"""
src/database.py

Supabase client initialization, storage ingestion, and session logging
for the Hiligaynon speech-based cognitive fatigue detection study.
"""

import uuid
from typing import Optional

import pandas as pd
import streamlit as st
from supabase import Client, create_client


@st.cache_resource
def get_supabase_client() -> Client:
    """Connects securely to Supabase using Streamlit secrets."""
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
        raise KeyError(
            "Missing Supabase credentials. Define SUPABASE_URL and SUPABASE_KEY in .streamlit/secrets.toml"
        )
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def save_respondent(
    respondent_id: str, birthplace: str, native_lang: str, freq_score: int
):
    """Upserts demographic verification data into the respondents table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "birthplace": birthplace,
        "native_language": native_lang,
        "hiligaynon_frequency_score": freq_score,
    }
    return supabase.table("respondents").upsert(data).execute()


def upload_audio_blob(file_bytes: bytes, filename: str) -> str:
    """Uploads audio bytes into audio-recordings storage bucket and returns public URL."""
    supabase = get_supabase_client()
    bucket_name = "audio-recordings"

    # Upload audio file bytes
    supabase.storage.from_(bucket_name).upload(
        path=filename,
        file=file_bytes,
        file_options={"content-type": "audio/wav", "upsert": "true"},
    )

    # Retrieve public URL
    return supabase.storage.from_(bucket_name).get_public_url(filename)


def log_session(
    respondent_id: str,
    task_level: str,
    ground_truth: int,
    predicted: Optional[str] = None,
    audio_url: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """Records session entries into the fatigue_session table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "task_level": task_level,
        "ground_truth_score": ground_truth,
        "predicted_fatigue": predicted,
        "audio_storage_url": audio_url,
    }
    if session_id:
        data["session_id"] = session_id

    return supabase.table("fatigue_session").insert(data).execute()


def fetch_all_sessions() -> pd.DataFrame:
    """Returns logged records as a Pandas DataFrame for analysis."""
    supabase = get_supabase_client()
    response = supabase.table("fatigue_session").select("*").execute()
    return pd.DataFrame(response.data)


def purge_session_state(session_state, destination_step: int = 0):
    """Clear staged participant data and reset session-scoped state for a fresh run."""
    session_id = session_state.get("session_id")
    session_key_prefixes = (
        "participant_audio_",
        "fatigue_rating_",
        "post_debrief_choice_",
        "language_selector_",
        "consent_check_",
        "birthplace_scope_",
        "birthplace_province_",
        "birthplace_locality_",
        "birthplace_manual_",
        "native_language_",
        "frequency_score_",
    )

    for key in list(session_state):
        if isinstance(key, str) and session_id and session_id in key and key.startswith(session_key_prefixes):
            del session_state[key]

    session_state["task_recordings"] = {}
    session_state["task_ratings"] = {}
    session_state["recorded_audio_bytes"] = None
    session_state["inference_results"] = {}
    session_state["respondent_id"] = f"WVSU-{uuid.uuid4().hex}"
    session_state["birthplace"] = ""
    session_state["birthplace_manual_text"] = ""
    session_state["birthplace_scope"] = "western_visayas"
    session_state["birthplace_province_code"] = "063000000"
    session_state["birthplace_needs_review"] = False
    session_state["native_language"] = None
    session_state["hiligaynon_frequency_score"] = 3
    session_state["samn_perelli_rating"] = None
    session_state["current_task_level"] = "Easy"
    session_state["task_index"] = 0
    session_state["screening_errors"] = []
    session_state["consent_accepted"] = False
    session_state["post_debrief_choice"] = None
    session_state["post_debrief_consent"] = False
    session_state["session_id"] = str(uuid.uuid4())
    session_state["current_step"] = destination_step
    return session_state