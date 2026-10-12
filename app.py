import streamlit as st

st.set_page_config(
    page_title="Speech Fatigue Detection",
    page_icon="🧠",
    layout="wide",
)

st.markdown(
    """
    <style>
        .stApp {
            background: #F8FAFC;
            color: #0F172A;
        }
        h1, h2, h3 { color: #1D4ED8; }
        h1 { border-left: 5px solid #2563EB; padding-left: 0.75rem; }
        .stCaption { color: #475569; }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .metric-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid rgba(37, 99, 235, 0.16);
            border-top: 4px solid #2563EB;
            border-radius: 18px;
            padding: 1.25rem 1.25rem;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.04);
            margin-bottom: 1rem;
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
        div.stButton > button[kind="primary"] {
            background: #2563EB;
            border-color: #2563EB;
            color: #FFFFFF;
        }
        div.stButton > button[kind="primary"]:hover {
            background: #1D4ED8;
            border-color: #1D4ED8;
        }
        div[data-testid="stPageLink-NavLink"] {
            background: #FFFFFF;
            border: 1px solid rgba(37, 99, 235, 0.22);
            border-left: 4px solid #2563EB;
            border-radius: 12px;
            color: #1E40AF;
        }
        div[data-testid="stPageLink-NavLink"]:hover {
            background: #EFF6FF;
            border-color: #2563EB;
        }
        header[data-testid="stHeader"] { display: none; }
        div[data-testid="stToolbar"], #MainMenu, footer,
        div[data-testid="stAppDeployButton"] { visibility: hidden; height: 0; }
        @media (max-width: 640px) {
            .block-container { padding: 1.5rem 0.75rem 1.5rem; }
            div[data-testid="stPageLink-NavLink"] { min-height: 48px; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page("pages/1_Data_Collection.py", title="Participant Portal", icon="📝"),
    st.Page("pages/2_Inference_Tool.py", title="Researcher Diagnostic Studio", icon="📊"),
]

participant_page, researcher_page = st.columns(2)
with participant_page:
    st.page_link(pages[0], label="Participant Portal", icon="📝", width="stretch")
with researcher_page:
    st.page_link(pages[1], label="Researcher Diagnostic Studio", icon="📊", width="stretch")

navigation = st.navigation(pages)
navigation.run()
