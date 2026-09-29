import streamlit as st
import pandas as pd
from supabase import create_client, Client

@st.cache_resource
def get_supabase_client() -> Client:
    """Connects securely to Supabase using Streamlit secrets."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def save_respondent(respondent_id: str, birthplace: str, native_lang: str, freq_score: int):
    """Inserts demographic verification data into the respondents table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "birthplace": birthplace,
        "native_language": native_lang,
        "hiligaynon_frequency_score": freq_score
    }
    return supabase.table("respondents").insert(data).execute()

def upload_audio_blob(file_bytes: bytes, filename: str) -> str:
    """Uploads audio bytes into audio-recordings storage bucket and returns public URL."""
    supabase = get_supabase_client()
    bucket_name = "audio-recordings"
    
    # Upload audio file bytes
    supabase.storage.from_(bucket_name).upload(
        path=filename,
        file=file_bytes,
        file_options={"content-type": "audio/wav", "upsert": "true"}
    )
    
    # Retrieve public URL
    return supabase.storage.from_(bucket_name).get_public_url(filename)

def log_session(respondent_id: str, task_level: str, ground_truth: int, predicted: str, audio_url: str):
    """Records session entries into the fatigue_session table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "task_level": task_level,
        "ground_truth_score": ground_truth,
        "predicted_fatigue": predicted,
        "audio_storage_url": audio_url
    }
    return supabase.table("fatigue_session").insert(data).execute()

def fetch_all_sessions() -> pd.DataFrame:
    """Returns logged records as a Pandas DataFrame for analysis."""
    supabase = get_supabase_client()
    response = supabase.table("fatigue_session").select("*").execute()
    return pd.DataFrame(response.data)
