import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Expected DataFrame columns when table is empty or on query error
EXPECTED_COLUMNS = [
    "session_id",
    "respondent_id",
    "task_level",
    "ground_truth_score",
    "predicted_fatigue",
    "audio_storage_url",
    "created_at",
]

@st.cache_resource
def get_supabase_client() -> Client:
    """Connects securely using st.secrets['SUPABASE_URL'] and st.secrets['SUPABASE_KEY']."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def save_respondent(respondent_id: str, birthplace: str, native_lang: str, freq_score: int):
    """Upserts participant demographic records into respondents table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "birthplace": birthplace,
        "native_language": native_lang,
        "hiligaynon_frequency_score": freq_score,
    }
    return supabase.table("respondents").upsert(data).execute()

def upload_audio_blob(file_bytes: bytes, filename: str) -> str:
    """Uploads standardized WAV bytes into audio-recordings storage bucket and returns public URL."""
    supabase = get_supabase_client()
    bucket_name = "audio-recordings"
    
    supabase.storage.from_(bucket_name).upload(
        path=filename,
        file=file_bytes,
        file_options={"content-type": "audio/wav", "upsert": "true"}
    )
    
    return supabase.storage.from_(bucket_name).get_public_url(filename)

def log_session(respondent_id: str, task_level: str, ground_truth: int, predicted: str, audio_url: str):
    """Inserts session records into fatigue_session table."""
    supabase = get_supabase_client()
    data = {
        "respondent_id": respondent_id,
        "task_level": task_level,
        "ground_truth_score": ground_truth,
        "predicted_fatigue": predicted,
        "audio_storage_url": audio_url,
    }
    return supabase.table("fatigue_session").insert(data).execute()

def fetch_all_sessions() -> pd.DataFrame:
    """
    Returns logged sessions as a Pandas DataFrame for the diagnostic studio.
    Returns an empty DataFrame with expected column names if the table is empty or if an exception occurs.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.table("fatigue_session").select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame(columns=EXPECTED_COLUMNS)
    except Exception as e:
        st.error(f"Error fetching fatigue sessions: {e}")
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

def delete_participant_data(respondent_id: str):
    """
    Ethics/Debriefing Helper: Deletes audio files from storage bucket and removes
    the corresponding participant rows from respondents and fatigue_session tables.
    """
    supabase = get_supabase_client()
    bucket_name = "audio-recordings"

    try:
        # 1. Fetch participant's session files to clean up audio storage
        response = (
            supabase.table("fatigue_session")
            .select("audio_storage_url")
            .eq("respondent_id", respondent_id)
            .execute()
        )

        if response.data:
            file_paths = []
            for row in response.data:
                url = row.get("audio_storage_url", "")
                if url:
                    # Extract stored filename from public URL
                    filename = url.split("/")[-1]
                    file_paths.append(filename)

            if file_paths:
                supabase.storage.from_(bucket_name).remove(file_paths)

        # 2. Delete from respondents table
        # Cascades to delete corresponding fatigue_session records automatically
        return supabase.table("respondents").delete().eq("respondent_id", respondent_id).execute()

    except Exception as e:
        st.error(f"Failed to delete data for participant {respondent_id}: {e}")
        return None
