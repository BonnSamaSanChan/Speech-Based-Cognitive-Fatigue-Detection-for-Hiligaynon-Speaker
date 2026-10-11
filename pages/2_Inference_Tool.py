import pandas as pd
import plotly.express as px
import streamlit as st

from src.audio_processor import extract_mel_spectrogram
from src.database import fetch_all_sessions

st.set_page_config(page_title="Researcher Diagnostic Studio", layout="wide")

st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; }
        h1, h2, h3 { color: #1D4ED8; }
        h1 { border-left: 5px solid #2563EB; padding-left: 0.75rem; }
        .card-panel {
            background: #FFFFFF;
            border: 1px solid rgba(37, 99, 235, 0.18);
            border-top: 4px solid #2563EB;
            border-radius: 18px;
            padding: 1.25rem;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.04);
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.4rem 0.8rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
        }
        .status-low { background: rgba(16, 185, 129, 0.12); color: #047857; }
        .status-moderate { background: rgba(245, 158, 11, 0.14); color: #b45309; }
        .status-high { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }
        div[data-testid="stFileUploaderDropzone"] {
            border: 1px dashed #60A5FA;
            border-radius: 14px;
            background: #EFF6FF;
        }
        div[data-testid="stFileUploaderDropzone"]:hover { border-color: #2563EB; }
        div.stButton > button[kind="primary"] {
            background: #2563EB;
            border-color: #2563EB;
            color: #FFFFFF;
        }
        div.stButton > button[kind="primary"]:hover {
            background: #1D4ED8;
            border-color: #1D4ED8;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Researcher Diagnostic Studio")
st.caption("Audio review, Mel-spectrogram analysis, attention diagnostics, and logged sessions")

uploaded_audio = st.file_uploader(
    "Upload recorded audio",
    type=["wav", "mp3", "m4a", "ogg"],
    help="Use a speech sample to inspect model features and fatigue prediction output.",
)

mel_spectrogram = None
if uploaded_audio is not None:
    st.audio(uploaded_audio)
    try:
        with st.spinner("Processing audio and extracting Mel-spectrogram..."):
            mel_spectrogram = extract_mel_spectrogram(uploaded_audio)
    except Exception as exc:
        st.error(f"Audio processing failed: {exc}")

left, right = st.columns([1.5, 1])

with left:
    st.markdown('<div class="card-panel">', unsafe_allow_html=True)
    st.subheader("Audio features")
    if uploaded_audio is None:
        st.info("Upload an audio recording to generate its Mel-spectrogram.")
    elif mel_spectrogram is not None:
        st.success("Audio processed: 16 kHz mono, voice activity trimmed, and padded or clipped to 15 seconds.")
        st.caption(f"Mel-spectrogram shape: {mel_spectrogram.shape[0]} bins × {mel_spectrogram.shape[1]} frames")
    st.markdown('</div>', unsafe_allow_html=True)

    if mel_spectrogram is not None:
        fig = px.imshow(
            mel_spectrogram,
            color_continuous_scale="Viridis",
            aspect="auto",
            labels={"x": "Time Frames", "y": "Mel Bins", "color": "Power (dB)"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown('<div class="card-panel">', unsafe_allow_html=True)
    st.subheader("Fatigue classification")
    st.info("Prediction and attention analysis are unavailable because a trained model is not connected yet.")
    st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Live session table")

session_df = pd.DataFrame(columns=["session_id", "respondent_id", "task_level", "ground_truth_score", "predicted_fatigue", "audio_storage_url"])
try:
    with st.spinner("Loading live session records..."):
        fetched_sessions = fetch_all_sessions()
    if fetched_sessions.empty:
        st.info("No participant sessions have been logged yet. Once a participant completes a task, their session row will appear here.")
    else:
        session_df = fetched_sessions.copy()
except Exception as exc:
    st.info("Live session data is unavailable until the Supabase credentials are configured. Once the database is connected, this table will populate automatically.")
    st.caption(f"Connection status: {exc}")

st.dataframe(session_df, use_container_width=True)

csv = session_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download dataset (.CSV)",
    data=csv,
    file_name="fatigue_session_logs.csv",
    mime="text/csv",
    disabled=session_df.empty,
)
