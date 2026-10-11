import pandas as pd
import streamlit as st
from supabase import create_client, Client

# Initialize Supabase Client
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- Task 4: Hardened fetch_all_sessions() ---
def fetch_all_sessions() -> pd.DataFrame:
    """
    Fetches all fatigue sessions. 
    Wraps query in exception handling to safely return an empty 
    DataFrame with expected schema if tables are empty or connection fails.
    """
    expected_columns = [
        "session_id",
        "respondent_id",
        "task_level",
        "ground_truth_score",
        "predicted_fatigue",
        "audio_storage_url",
        "created_at"
    ]
    
    try:
        response = supabase.table("fatigue_session").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame(columns=expected_columns)
    except Exception as e:
        st.warning(f"Unable to fetch database sessions: {e}")
        return pd.DataFrame(columns=expected_columns)

# --- Task 5: Cloud Purge Function (Thesis Appendix C Compliance) ---
def delete_participant_data(respondent_id: str) -> bool:
    """
    Removes participant audio files from storage and purges database records
    when a participant invokes withdrawal.
    """
    try:
        # 1. Fetch audio file URLs associated with participant
        sessions = (
            supabase.table("fatigue_session")
            .select("audio_storage_url")
            .eq("respondent_id", respondent_id)
            .execute()
        )
        
        # 2. Extract relative paths and remove files from audio-recordings storage bucket
        file_paths = []
        for session in sessions.data:
            url = session.get("audio_storage_url", "")
            if "audio-recordings/" in url:
                file_path = url.split("audio-recordings/")[-1]
                file_paths.append(file_path)
                
        if file_paths:
            supabase.storage.from_("audio-recordings").remove(file_paths)

        # 3. Delete respondent from database
        # (ON DELETE CASCADE automatically purges matching fatigue_session rows)
        supabase.table("respondents").delete().eq("respondent_id", respondent_id).execute()
        return True

    except Exception as e:
        st.error(f"Failed to purge data for {respondent_id}: {e}")
        return False
