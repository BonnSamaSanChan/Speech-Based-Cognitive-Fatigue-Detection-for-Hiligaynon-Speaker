"""
src/audio_processor.py

Production acoustic signal processing and feature extraction pipeline for Hiligaynon
cognitive fatigue detection. Handles in-memory format standardization, energy-based VAD,
fixed 15.0-second temporal windowing, and deterministic (128, 1500, 1) Mel-spectrogram tensor extraction.
"""

import io
from typing import BinaryIO, Union
import librosa
import numpy as np
from pydub import AudioSegment
import soundfile as sf

# Core Acoustic Parameters
TARGET_SR: int = 16000
TARGET_DURATION: float = 15.0
TARGET_SAMPLES: int = int(TARGET_SR * TARGET_DURATION)  # 240,000 samples
N_FFT: int = 400          # 25 ms window at 16 kHz
HOP_LENGTH: int = 160     # 10 ms step at 16 kHz
N_MELS: int = 128         # 128 Mel-frequency bins
TARGET_FRAMES: int = 1500 # Deterministic temporal dimension


def standardize_audio(file_input: Union[bytes, BinaryIO, str]) -> bytes:
    """
    Standardize incoming audio from arbitrary formats (.mp3, .m4a, .ogg, .wav)
    into a uniform 16 kHz mono WAV byte stream.

    Parameters:
        file_input: Raw audio bytes, a file-like buffer, or a local file path.

    Returns:
        bytes: Raw WAV audio bytes formatted to 16 kHz, 16-bit mono.
    """
    if isinstance(file_input, (bytes, bytearray)):
        audio_stream = io.BytesIO(file_input)
        segment = AudioSegment.from_file(audio_stream)
    elif hasattr(file_input, "read"):
        file_input.seek(0)
        audio_stream = io.BytesIO(file_input.read())
        segment = AudioSegment.from_file(audio_stream)
    elif isinstance(file_input, str):
        segment = AudioSegment.from_file(file_input)
    else:
        raise TypeError("Unsupported file_input type for standardization.")

    # Convert to 16 kHz, single channel (mono), 16-bit depth
    segment = segment.set_frame_rate(TARGET_SR).set_channels(1).set_sample_width(2)

    output_buffer = io.BytesIO()
    segment.export(output_buffer, format="wav")
    return output_buffer.getvalue()


def load_and_trim_audio(
    audio_source: Union[str, bytes, BinaryIO],
    top_db: int = 20
) -> np.ndarray:
    """
    Load an audio source into a 1D NumPy array at 16 kHz, trim leading/trailing
    silence using Voice Activity Detection (VAD), and normalize peak amplitude.

    Parameters:
        audio_source: File path, raw bytes, or BytesIO buffer of audio.
        top_db: Decibel threshold below reference peak to register as silence.

    Returns:
        np.ndarray: Normalized 1D float32 audio waveform.
    """
    if isinstance(audio_source, (bytes, bytearray)):
        buffer = io.BytesIO(audio_source)
        y, sr = sf.read(buffer, dtype="float32")
    elif hasattr(audio_source, "read"):
        audio_source.seek(0)
        buffer = io.BytesIO(audio_source.read())
        y, sr = sf.read(buffer, dtype="float32")
    elif isinstance(audio_source, str):
        y, sr = sf.read(audio_source, dtype="float32")
    else:
        raise TypeError("Unsupported audio_source type.")

    # Convert multi-channel audio to mono if necessary
    if y.ndim > 1:
        y = np.mean(y, axis=1)

    # Resample if sample rate does not match target
    if sr != TARGET_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR)

    # Voice Activity Detection: trim leading and trailing silence
    y_trimmed, _ = librosa.effects.trim(y, top_db=top_db)

    # Fallback to original if aggressive trimming removes all content
    if len(y_trimmed) == 0:
        y_trimmed = y

    # Peak amplitude normalization [-1.0, 1.0]
    y_norm = librosa.util.normalize(y_trimmed)

    return y_norm.astype(np.float32)


def enforce_fixed_duration(
    y: np.ndarray,
    target_samples: int = TARGET_SAMPLES
) -> np.ndarray:
    """
    Enforce a deterministic length of 240,000 samples (15.0 seconds).
    Symmetrically zero-pads shorter signals; center-clips longer signals.

    Parameters:
        y: 1D audio waveform array.
        target_samples: Exact number of samples required.

    Returns:
        np.ndarray: Waveform locked to target_samples length.
    """
    current_length = len(y)

    if current_length < target_samples:
        total_pad = target_samples - current_length
        pad_left = total_pad // 2
        pad_right = total_pad - pad_left
        return np.pad(y, (pad_left, pad_right), mode="constant", constant_values=0.0)

    if current_length > target_samples:
        start_index = (current_length - target_samples) // 2
        return y[start_index : start_index + target_samples]

    return y


def extract_mel_spectrogram(
    audio_source: Union[str, bytes, BinaryIO],
    top_db: int = 20
) -> np.ndarray:
    """
    Full pipeline to produce a 128-bin decibel Mel-spectrogram locked to exactly
    1,500 frames for UI rendering and neural network ingestion.

    Parameters:
        audio_source: Audio file path, bytes, or file-like buffer.
        top_db: Decibel threshold for VAD trimming.

    Returns:
        np.ndarray: 2D array of shape (128, 1500) representing log-Mel power.
    """
    # 1. Decode common WAV inputs directly; use FFmpeg-backed normalization for other formats.
    try:
        y = load_and_trim_audio(audio_source, top_db=top_db)
    except (RuntimeError, ValueError):
        standardized_audio = standardize_audio(audio_source)
        y = load_and_trim_audio(standardized_audio, top_db=top_db)

    # 2. Enforce 15.0-second fixed duration
    y_fixed = enforce_fixed_duration(y, target_samples=TARGET_SAMPLES)

    # 3. Compute Mel-spectrogram
    mel_spec = librosa.feature.melspectrogram(
        y=y_fixed,
        sr=TARGET_SR,
        n_fft=N_FFT,
        hop_length=HOP_LENGTH,
        n_mels=N_MELS,
        center=True
    )

    # 4. Convert to decibel scale
    mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

    # 5. Lock temporal frames to exactly 1,500 frames
    current_frames = mel_spec_db.shape[1]
    if current_frames >= TARGET_FRAMES:
        mel_spec_db = mel_spec_db[:, :TARGET_FRAMES]
    else:
        pad_width = TARGET_FRAMES - current_frames
        mel_spec_db = np.pad(
            mel_spec_db,
            ((0, 0), (0, pad_width)),
            mode="constant",
            constant_values=mel_spec_db.min()
        )

    return mel_spec_db.astype(np.float32)


def prepare_model_tensor(mel_spec_db: np.ndarray) -> np.ndarray:
    """
    Reshape a (128, 1500) Mel-spectrogram into a 4D batch tensor of shape
    (1, 128, 1500, 1) suitable for TensorFlow/Keras Conv2D inference.

    Parameters:
        mel_spec_db: 2D Mel-spectrogram array.

    Returns:
        np.ndarray: 4D tensor with shape (1, 128, 1500, 1) in float32.
    """
    if mel_spec_db.shape != (N_MELS, TARGET_FRAMES):
        raise ValueError(
            f"Expected spectrogram shape ({N_MELS}, {TARGET_FRAMES}), got {mel_spec_db.shape}"
        )
    return np.expand_dims(mel_spec_db, axis=(0, -1)).astype(np.float32)
