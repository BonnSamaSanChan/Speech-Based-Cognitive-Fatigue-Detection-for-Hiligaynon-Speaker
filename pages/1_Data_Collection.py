import json
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import streamlit as st

from src.audio_processor import standardize_audio
from src.database import (
    delete_participant_data,
    log_session,
    purge_session_state,
    save_respondent,
    upload_audio_blob,
)

st.set_page_config(page_title="Participant Data Collection", layout="wide")

st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; }
        h1, h2, h3 { color: #1D4ED8; }
        h1 { border-left: 5px solid #2563EB; padding-left: 0.75rem; }
        .wizard-shell {
            background: #FFFFFF;
            border: 1px solid rgba(37, 99, 235, 0.18);
            border-top: 4px solid #2563EB;
            border-radius: 18px;
            padding: 1.5rem;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.04);
        }
        .study-banner {
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            border: 1px solid rgba(37, 99, 235, 0.18);
            border-left: 5px solid #2563EB;
            border-radius: 16px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
        }
        .study-banner-tag {
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 700;
            color: #1D4ED8;
        }
        .study-banner-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: #0F172A;
            margin-top: 0.35rem;
        }
        .study-banner-subtitle {
            font-size: 0.95rem;
            color: #475569;
            margin-top: 0.2rem;
        }
        .metric-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid rgba(37, 99, 235, 0.16);
            border-left: 4px solid #2563EB;
            border-radius: 18px;
            padding: 1rem 1.25rem;
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
        div[data-testid="stProgress"] > div > div > div { background: #2563EB; }
        div.stButton > button,
        div[data-testid="stFileUploader"] button,
        div[data-testid="stFileUploaderDropzone"] {
            min-height: 48px;
        }
        div[data-testid="stRadio"] label {
            min-height: 48px;
            align-items: center;
        }
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"]:focus-within,
        div[data-testid="stTextInput"] input:focus {
            border-color: #2563EB;
            box-shadow: 0 0 0 1px #2563EB;
        }
        @media (max-width: 640px) {
            .block-container { padding: 1.5rem 0.75rem 1.5rem; }
            .study-banner { padding: 0.9rem; }
            .study-banner-title { font-size: 1.2rem; }
            div[data-testid="stRadio"] [role="radiogroup"] { gap: 0.25rem; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


DEFAULTS = {
    "session_id": str(uuid.uuid4()),
    "respondent_id": f"WVSU-{uuid.uuid4().hex}",
    "language": "Hiligaynon",
    "current_step": 0,
    "task_index": 0,
    "current_task_level": "Easy",
    "recorded_audio_bytes": None,
    "task_recordings": {},
    "samn_perelli_rating": None,
    "task_ratings": {},
    "ingested_tasks": {},
    "inference_results": {},
    "persistence_error": None,
    "consent_accepted": False,
    "post_debrief_consent": False,
    "pending_cloud_purge": None,
    "cloud_purge_error": None,
    "post_debrief_choice": None,
    "birthplace": "",
    "birthplace_scope": "western_visayas",
    "birthplace_province_code": "063000000",
    "birthplace_needs_review": False,
    "birthplace_manual_text": "",
    "native_language": None,
    "hiligaynon_frequency_score": 3,
    "screening_errors": [],
}


for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

if not st.session_state.respondent_id:
    st.session_state.respondent_id = f"WVSU-{uuid.uuid4().hex}"


TASK_LEVELS = ["Easy", "Moderate", "Intensive"]
SAMN_SCALE = [1, 2, 3, 4, 5, 6, 7]
LANGUAGES = ["Hiligaynon", "English"]
NATIVE_LANGUAGES = ["Hiligaynon", "Kinaray-a", "Filipino", "English", "Other"]
WESTERN_VISAYAS_PROVINCES = {
    "060400000": "Aklan",
    "060600000": "Antique",
    "061900000": "Capiz",
    "063000000": "Iloilo",
    "064500000": "Negros Occidental",
    "067900000": "Guimaras",
}
SCREENING_TEXT = {
    "English": {
        "language_label": "Preferred language / Pinili nga lenguahe",
        "step": "Step 2 · Screening",
        "intro": "Complete the required participant screening fields. The study is currently recruiting native Hiligaynon speakers.",
        "language": "Preferred language for the rest of the questionnaire",
        "respondent_id": "Confidential participant code (generated automatically)",
        "birthplace": "City or municipality of birth (required)",
        "birthplace_scope": "Where were you born?",
        "birthplace_scopes": {"western_visayas": "Western Visayas", "philippines": "Elsewhere in the Philippines", "outside_ph": "Outside the Philippines"},
        "birthplace_manual": "Enter your birthplace for researcher verification",
        "birthplace_pending": "This location will be marked for manual verification; it is not checked against the PSGC.",
        "birthplace_fallback": "The official locality list is temporarily unavailable. Enter your city or municipality below; the research team will verify it manually.",
        "birthplace_province": "Province",
        "birthplace_locality": "City or municipality",
        "birthplace_unavailable": "The official locality list is unavailable. Check your connection and try again; you cannot continue without a verified selection.",
        "native_language": "Primary native language (required)",
        "frequency": "How often do you speak Hiligaynon daily? (required)",
        "frequency_anchor": "1 · Rarely     2 · Sometimes     3 · About half the day     4 · Often     5 · Almost always",
        "frequency_selected": "Selected frequency: {value} · {anchor}",
        "frequency_values": ["Rarely", "Sometimes", "About half the day", "Often", "Almost always"],
        "previous": "Previous",
        "next": "Next",
        "required_birthplace": "Enter your birthplace.",
        "required_manual_birthplace": "Enter your birthplace, or select a Philippine locality.",
        "invalid_birthplace": "Select a city or municipality from the official list.",
        "required_native": "Select your primary native language.",
        "ineligible": "This study is currently limited to native Hiligaynon speakers. You cannot continue with the selected language.",
        "native_names": {"Hiligaynon": "Hiligaynon", "Kinaray-a": "Kinaray-a", "Filipino": "Filipino", "English": "English", "Other": "Other"},
    },
    "Hiligaynon": {
        "step": "Lakang 2 · Screening",
        "intro": "Kompletoha ang mga kinahanglanon nga impormasyon. Sa subong, nagapangita ang pagtuon sang mga lumad nga manughambal sang Hiligaynon.",
        "language": "Pinili nga lenguahe para sa nabilin nga questionnaire",
        "respondent_id": "Kompidensyal nga kodigo sang partisipante (ginhimo sing automatic)",
        "birthplace": "Syudad ukon munisipalidad nga natawhan (kinahanglan)",
        "birthplace_scope": "Diin ka natawhan?",
        "birthplace_scopes": {"western_visayas": "Western Visayas", "philippines": "Sa iban nga bahin sang Pilipinas", "outside_ph": "Sa guwa sang Pilipinas"},
        "birthplace_manual": "Isulat ang lugar nga natawhan para mapanghimatuudan sang manug-usisa",
        "birthplace_pending": "Markahan ini nga lugar para panghimatuudan sang manug-usisa; wala ini nasusi sa PSGC.",
        "birthplace_fallback": "Indi makuha temporaryo ang opisyal nga listahan sang mga lugar. Isulat sa idalom ang imo syudad ukon munisipalidad agod mapanghimatuudan sang research team.",
        "birthplace_province": "Probinsya",
        "birthplace_locality": "Syudad ukon munisipalidad",
        "birthplace_unavailable": "Indi makuha ang opisyal nga listahan sang mga lugar. Usisaa ang koneksyon kag magtilaw liwat; indi ka makapadayon kon wala sing napilian nga ginpanghimatuudan.",
        "native_language": "Pangunahon nga lumad nga lenguahe (kinahanglan)",
        "frequency": "Daw ano ka permi ka nagahambal sang Hiligaynon kada adlaw? (kinahanglan)",
        "frequency_anchor": "1 · Talagsa     2 · Kon kaisa     3 · Mga tunga sang adlaw     4 · Perme     5 · Halos permi",
        "frequency_selected": "Napilian nga kadamuon: {value} · {anchor}",
        "frequency_values": ["Talagsa", "Kon kaisa", "Mga tunga sang adlaw", "Perme", "Halos permi"],
        "previous": "Balik",
        "next": "Sunod",
        "required_birthplace": "Isulat ang lugar nga natawhan.",
        "required_manual_birthplace": "Isulat ang lugar nga natawhan ukon magpili sang lugar sa Pilipinas.",
        "invalid_birthplace": "Pilia ang syudad ukon munisipalidad halin sa opisyal nga listahan.",
        "required_native": "Pilia ang pangunahon nga lumad nga lenguahe.",
        "ineligible": "Para lamang ini subong sa mga lumad nga manughambal sang Hiligaynon. Indi ka makapadayon sa napilian nga lenguahe.",
        "native_names": {"Hiligaynon": "Hiligaynon", "Kinaray-a": "Kinaray-a", "Filipino": "Filipino", "English": "Ingles", "Other": "Iban pa"},
    },
}
SCREENING_TEXT["English"]["native_names"] = {
    "Hiligaynon": "Hiligaynon", "Kinaray-a": "Kinaray-a", "Filipino": "Filipino", "English": "English", "Other": "Other"
}
UI_TEXT = {
    "English": {
        "step_task": "Step 3 · Cognitive Tasks",
        "task_level": "Select task level",
        "task_names": {"Easy": "Easy", "Moderate": "Moderate", "Intensive": "Intensive"},
        "task_instructions": "Read each question and answer every question aloud while recording. Upload one audio file containing all responses for this part.",
        "prompt_label": "Question",
        "draft_notice": "Question wording and difficulty progression are drafts; confirm them against the approved thesis protocol before participant recruitment.",
        "upload": "Upload or record speech audio",
        "upload_help": "Accepted formats: WAV, MP3, M4A, and OGG.",
        "upload_processing": "Validating the uploaded recording...",
        "audio_ready": "Audio is ready for this task.",
        "audio_required": "Upload a recording before continuing.",
        "audio_error": "The audio file is empty. Upload a non-empty recording to continue.",
        "next_rating": "Next · Fatigue rating",
        "step_rating": "Step 4 · Samn–Perelli Fatigue Rating",
        "rating_intro": "Rate your current fatigue level immediately after the task.",
        "rating_prompt": "Choose the description that best matches how you feel.",
        "rating_anchors": ["Fully alert, wide awake", "Very lively, responsive", "Okay, somewhat fresh", "A little tired", "Moderately tired", "Extremely tired", "Completely exhausted"],
        "next_debrief": "Next · Debriefing",
        "step_debrief": "Step 5 · Debriefing",
        "thanks": "Thank you for completing the task.",
        "disclosure_title": "Disclosure",
        "disclosure": "The true target of this study is cognitive fatigue as reflected in speech. The task prompts were used to elicit speech while varying cognitive effort; this specific focus was not fully explained before the task to reduce response bias.",
        "withdrawal": "You may now ask questions or withdraw. Your screening answers, fatigue ratings, and recordings have been submitted to the study database and audio storage. If you withdraw or decline use of your data, the app will request deletion; ask the research team to confirm removal if the app reports a deletion problem.",
        "participant_code": "Confidential participant code",
        "task_label": "Task level",
        "rating_label": "Samn–Perelli rating",
        "recording_label": "Recording",
        "recording_present": "Uploaded",
        "recording_missing": "Not uploaded",
        "no_rating": "Not provided",
        "post_consent": "After learning the true purpose, I agree that my data may be used for the study.",
        "post_consent_yes": "Your agreement is recorded with your study data in the research database and audio storage, in accordance with the approved study protocol.",
        "post_consent_no": "Choosing this option requests deletion of your submitted study records and stored recordings, and clears your active app session.",
        "reset": "Reset session",
        "native_names": {"Hiligaynon": "Hiligaynon", "Kinaray-a": "Kinaray-a", "Filipino": "Filipino", "English": "English", "Other": "Other"},
        "scale_labels": ["1 · Fully alert", "2 · Very lively", "3 · Okay, somewhat fresh", "4 · A little tired", "5 · Moderately tired", "6 · Extremely tired", "7 · Completely exhausted"],
    },
    "Hiligaynon": {
        "language_label": "Pinili nga lenguahe / Preferred language",
        "step_task": "Lakang 3 · Mga Buluhaton sa Panghunahuna",
        "task_level": "Pilia ang kabudlayon sang buluhaton",
        "task_names": {"Easy": "Mahapos", "Moderate": "Katamtaman", "Intensive": "Mabudlay"},
        "task_instructions": "Basaha ang kada pamangkot kag sabta ini sing matunog samtang nagarekord. I-upload ang isa ka audio file nga may tanan mo nga sabat sa sini nga bahin.",
        "prompt_label": "Pamangkot",
        "draft_notice": "Draft pa ang mga pulong kag kabudlayon sang buluhaton; ipasibu ini sa gin-aprubahan nga thesis protocol antes mag-recruit sang partisipante.",
        "upload": "Mag-upload ukon magrekord sang audio sang paghambal",
        "upload_help": "WAV, MP3, M4A, kag OGG lamang.",
        "upload_processing": "Gina-usisa ang recording nga gin-upload...",
        "audio_ready": "Andam na ang audio para sa sini nga buluhaton.",
        "audio_required": "Mag-upload sang recording antes magpadayon.",
        "audio_error": "Wala sing sulod ang audio file. Mag-upload sang recording nga may sulod agod makapadayon.",
        "next_rating": "Sunod · Marka sang kakapoy",
        "step_rating": "Lakang 4 · Marka sang Kakapoy nga Samn–Perelli",
        "rating_intro": "Markahi ang imo kakapoy pagkatapos gid sang buluhaton.",
        "rating_prompt": "Pilia ang deskripsyon nga pinakabagay sa imo pamatyag.",
        "rating_anchors": ["Bugtaw gid", "Buhi kag madinalag-on", "Maayo kag medyo presko", "Medyo kapoy", "Kasarang nga kapoy", "Kapoy gid", "Gid-ka-kapoy"],
        "next_debrief": "Sunod · Pagpaathag pagkatapos sang buluhaton",
        "step_debrief": "Lakang 5 · Pagpaathag pagkatapos sang buluhaton",
        "thanks": "Salamat sa paghuman sang buluhaton.",
        "disclosure_title": "Pagpahayag",
        "disclosure": "Ang matuod nga ginatuon sang sini nga pagtuon amo ang kakapoy sang panghunahuna nga makita sa paghambal. Gin-gamit ang mga buluhaton agod makakuha sang mga halimbawa sang paghambal samtang nagabag-o ang panikasog sang panghunahuna; wala ginpaathag sing bug-os ang sini nga tuyo antes sang buluhaton agod malikawan ang pagbag-o sang sabat.",
        "withdrawal": "Mahimo ka mamangkot ukon magbiya sa pagtuon. Ginpasa na sa database kag audio storage sang pagtuon ang imo mga sabat sa screening, marka sang kakapoy, kag mga recording. Kon magbiya ka ukon indi mouyon nga gamiton ang datos, magapangayo ang app sang pag-delete; kontaka ang research team agod kumpirmahon ang pagtangtang kon may problema ang app.",
        "participant_code": "Kompidensyal nga kodigo sang partisipante",
        "task_label": "Kabudlayon sang buluhaton",
        "rating_label": "Marka nga Samn–Perelli",
        "recording_label": "Recording",
        "recording_present": "Na-upload",
        "recording_missing": "Wala na-upload",
        "no_rating": "Wala ginhatag",
        "post_consent": "Pagkatapos mahibaluan ang matuod nga katuyuan, nagauyon ako nga gamiton ang akon datos para sa pagtuon.",
        "post_consent_yes": "Irekord ang imo pag-uyon upod sa datos sa database kag audio storage sang pagtuon suno sa gin-aprubahan nga study protocol.",
        "post_consent_no": "Kon pilion ini, magapangayo ang app sang pagtangtang sang imo mga rekord kag recording sa pagtuon, kag kuhaon man ang datos sa aktibo nga sesyon sang app.",
        "reset": "Sugdan liwat ang sesyon",
        "native_names": {"Hiligaynon": "Hiligaynon", "Kinaray-a": "Kinaray-a", "Filipino": "Filipino", "English": "Ingles", "Other": "Iban pa"},
        "scale_labels": ["1 · Bugtaw gid", "2 · Buhi kag madinalag-on", "3 · Maayo kag medyo presko", "4 · Medyo kapoy", "5 · Kasarang nga kapoy", "6 · Kapoy gid", "7 · Gid-ka-kapoy"],
    },
}
SAMN_LABELS = {
    "English": ["Fully alert, wide awake", "Very lively, responsive, but not at peak", "Okay, somewhat fresh", "A little tired, less than fresh", "Moderately tired, let down", "Extremely tired, very difficult to concentrate", "Completely exhausted, unable to function effectively"],
    "Hiligaynon": ["Bugtaw gid", "Buhi kag masaligon, pero indi pa pinakamaayo", "Maayo ang pamatyag kag medyo presko", "Medyo kapoy, indi na pareho ka-presko", "Kasarang nga kapoy kag daw naluya", "Kapoy gid kag mabudlay magkonsentrar", "Gid-ka-kapoy kag indi na makatrabaho sing epektibo"],
}
FLOW_TEXT = {
    "English": {
        "app_title": "Participant Data Collection",
        "language_label": "Preferred language",
        "language_title": "Choose your language",
        "language_intro": "Select the language you prefer for the consent form and the entire questionnaire.",
        "language_continue": "Continue to consent",
        "consent_title": "Step 1 · Informed Consent",
        "consent_ack": "I have read and understood this information, and I voluntarily agree to participate.",
        "consent_next": "Agree and continue",
        "consent_notice": "The Hiligaynon translation is a draft. Have a fluent speaker and the approving ethics committee review it before recruitment.",
        "progress": ["Language", "Consent", "Screening", "Tasks", "Debrief"],
        "task_order": "Part {part} · Task {number} of 3 · {task}",
        "task_complete": "Recording ready. You will rate fatigue immediately after this task.",
        "recording_present": "Uploaded",
        "recording_missing": "Not uploaded",
        "upload_title": "Upload speech recording",
        "upload_help": "Choose the speech recording for this task. Supported: WAV, MP3, M4A, OGG. Maximum upload size: 50 MB. Re-uploading replaces this task's recording only.",
        "next_rating": "Continue to fatigue rating",
        "rating_order": "Fatigue rating {number} of 3",
        "next_task": "Save rating and continue to next task",
        "finish_tasks": "Save rating and continue to debriefing",
        "frequency_values": ["Rarely", "Sometimes", "About half the day", "Often", "Almost always"],
        "withdraw": "Withdraw and clear this session",
        "withdraw_title": "Session withdrawn",
        "withdraw_body": "Your active app session has been cleared. The app requested deletion of your study records and stored recordings.",
        "post_consent_prompt": "After this disclosure, do you agree to the use of these data for the study?",
        "post_consent_options": {"agree": "I agree", "decline": "I do not agree; clear my session data"},
        "finish_debrief": "Confirm choice",
        "complete_title": "Questionnaire complete",
        "complete_body": "Your agreement was recorded with your study data in the research database and audio storage.",
        "declined_title": "Session data cleared",
        "declined_body": "You declined post-debriefing data use. Active session answers and uploaded recordings have been cleared.",
        "reset": "Start a new session",
        "manual_birthplace_notice": "This location is pending researcher verification; do not treat it as PSGC-verified.",
        "birthplace_other": "Enter a birthplace for verification",
    },
    "Hiligaynon": {
        "app_title": "Pagkolekta sang Datos sang Partisipante",
        "language_label": "Pinili nga lenguahe",
        "language_title": "Pilia ang imo lenguahe",
        "language_intro": "Pilia ang lenguahe nga gusto mo gamiton sa pagsabat sang questionnaire.",
        "language_continue": "Magpadayon sa consent",
        "consent_title": "Lakang 1 · Pagtugot nga May Kahibalo",
        "consent_ack": "Nabasa ko kag naintindihan ang impormasyon; boluntaryo ako nga nagauyon mag-apil.",
        "consent_next": "Nagauyon ako kag magapadayon",
        "consent_notice": "Draft pa ang Hiligaynon nga hubad. Ipasusi ini sa maayo maghambal sang Hiligaynon kag sa ethics committee antes mag-recruit.",
        "progress": ["Lenguahe", "Consent", "Screening", "Mga Buluhaton", "Pagpaathag"],
        "task_order": "Part {part} · Buluhaton {number} sa 3 · {task}",
        "task_complete": "Andam na ang recording. Markahi ang kakapoy pagkatapos gid sini nga buluhaton.",
        "recording_present": "Na-upload",
        "recording_missing": "Wala na-upload",
        "upload_title": "Mag-upload sang recording sang paghambal",
        "upload_help": "Pilia ang recording sang paghambal para sa sini nga buluhaton. Ginasuportahan: WAV, MP3, M4A, OGG. Pinakadaku nga upload: 50 MB. Ang bag-o nga file magailis lamang sang recording para sa sini nga buluhaton.",
        "next_rating": "Padayon sa marka sang kakapoy",
        "rating_order": "Marka sang kakapoy {number} sa 3",
        "next_task": "Itipig ang marka kag padayon sa masunod nga buluhaton",
        "finish_tasks": "Itipig ang marka kag padayon sa pagpaathag",
        "frequency_values": ["Talagsa", "Kon kaisa", "Mga tunga sang adlaw", "Perme", "Halos permi"],
        "withdraw": "Magbiya kag kuhaa ang datos sa sini nga sesyon",
        "withdraw_title": "Nagbiya ka sa sesyon",
        "withdraw_body": "Ginkuha na ang datos sa aktibo nga sesyon sang app. Nagpangayo ang app sang pagtangtang sang imo mga rekord kag recording sa pagtuon.",
        "post_consent_prompt": "Pagkatapos sini nga pagpaathag, nagauyon ka bala nga gamiton ang datos para sa pagtuon?",
        "post_consent_options": {"agree": "Nagauyon ako", "decline": "Indi ako nagauyon; kuhaa ang akon datos sa sesyon"},
        "finish_debrief": "Kumpirmahon ang akon pilian",
        "complete_title": "Natapos ang questionnaire",
        "complete_body": "Narekord ang imo pag-uyon upod sa datos sa database kag audio storage sang pagtuon.",
        "declined_title": "Ginkuha ang datos sang sesyon",
        "declined_body": "Wala ka nagauyon sa paggamit sang datos pagkatapos sang pagpaathag. Ginkuha na ang aktibo nga mga sabat kag recording.",
        "reset": "Magsugod sang bag-o nga sesyon",
        "manual_birthplace_notice": "Naga hulat ini sang panghimatuud sang manug-usisa; wala ini ginpanghimatuudan sang PSGC.",
        "birthplace_other": "Isulat ang lugar nga natawhan para panghimatuudan",
    },
}
CONSENT_TEXT = {
    "English": {
        "purpose_title": "Purpose",
        "purpose": "This study examines speech and responses during short cognitive tasks. Some specific study details are withheld until the debriefing so they do not influence responses.",
        "participation_title": "What participation involves",
        "participation": "You will answer screening questions, complete three spoken cognitive tasks in order, upload a voice recording after each task, and rate your fatigue immediately after each recording. These activities may cause temporary mental effort or tiredness.",
        "privacy_title": "Confidentiality and data handling",
        "privacy": "Your name is not requested. A confidential participant code is generated automatically. Voice recordings can identify you. Screening answers and fatigue ratings are stored in the study database, and recordings are stored in the study's audio storage for analysis. Only authorized study personnel should access these records. Approved security, access, storage, and retention arrangements must be in place before recruitment.",
        "withdraw_title": "Voluntary participation and withdrawal",
        "withdraw": "Participation is voluntary. You may withdraw at any time without penalty by using the withdrawal control. It clears the active questionnaire answers and recordings from this app session. Ask the research team about removal of any data already submitted under the approved study protocol.",
    },
    "Hiligaynon": {
        "purpose_title": "Katuyuan",
        "purpose": "Ginausisa sang sini nga pagtuon ang paghambal kag mga sabat samtang nagahimo sang malip-ot nga mga buluhaton sa panghunahuna. Ang pila ka partikular nga detalye sang pagtuon ipahibalo pagkatapos sang mga buluhaton agod indi ini makaapekto sa imo mga sabat.",
        "participation_title": "Ano ang nalakip sa pag-apil",
        "participation": "Masabat ka sang mga pamangkot sa screening, makompleto sang tatlo ka ginahambal nga buluhaton sa panghunahuna sunod-sunod, mag-upload sang recording sang tingog pagkatapos sang tagsa ka buluhaton, kag markahan ang imo kakapoy gilayon pagkatapos sang tagsa ka recording. Mahimo ini magdulot sang temporaryo nga panikasog sang hunahuna ukon kakapoy.",
        "privacy_title": "Kompidensyalidad kag pagdumala sang datos",
        "privacy": "Wala ginapangayo ang imo ngalan. Awtomatiko nga ginahimo ang kompidensyal nga kodigo sang partisipante. Mahimo makakilala sa imo paagi sa imo tingog. Itipig sa database sang pagtuon ang imo mga sabat sa screening kag marka sang kakapoy, kag itipig sa audio storage ang imo mga recording para sa pag-usisa. Awtorisado lamang nga mga miyembro sang pagtuon ang dapat makakita sini nga mga rekord. Dapat may gin-aprubahan nga kahimusan para sa seguridad, access, pagtipig, kag retention antes magsugod ang recruitment.",
        "withdraw_title": "Boluntaryo nga pag-apil kag pag-atras",
        "withdraw": "Boluntaryo ang imo pag-apil. Mahimo ka mag-atras bisan san-o nga wala sing penalidad paagi sa withdrawal control. Kuhaon sini ang aktibo nga mga sabat kag recording sa sesyon sang app, kag magapangayo ini sang pagtangtang sang datos nga naipasa na sa database sang pagtuon. Pamangkuta ang research team kon may problema sa pagkumpirma sang pagtangtang.",
    },
}
TASK_PROMPTS = {
    "Easy": {
        "hiligaynon": [
            "Diin ka natawo kag diin ka nagdaku?",
            "Ano ang ginakuha mo nga kurso?",
            "Ano ang paborito mo nga pagkaon kag ngaa?",
            "Ano ang imo ginahimo kon may libre ka nga oras?",
            "Sin-o ang imo permi ginakaupod sa eskwelahan?",
            "Ano ang paborito mo nga subject?",
            "I-describe ang imo kaugalingon sa tatlo ka pulong.",
            "Ipaathag kon ano ang kasagarang adlaw mo sa eskwelahan.",
        ],
        "english": [
            "Where were you born, and where did you grow up?",
            "What course or program are you studying?",
            "What is your favorite food, and why?",
            "What do you usually do in your free time?",
            "Who do you usually spend time with at school?",
            "What is your favorite subject?",
            "Describe yourself in three words.",
            "Describe a typical day for you at school.",
        ],
    },
    "Moderate": {
        "hiligaynon": [
            "Ano ang sabat sang 12 + 15? Ipaathag kon paano mo ini ginkwenta.",
            "Ano ang sabat sang 45 - 19? Ipaathag ang imo pagsolbar.",
            "Ano ang sabat sang 8 x 7? Ipaathag ang imo pagsolbar.",
            "Ano ang sabat sang 64 / 8? Ipaathag ang imo pagsolbar.",
            "Ngaa importante ang edukasyon para sa imo?",
            "Ipaathag kon paano ka nagahanda para sa exam.",
            "Ano ang imo ginahimo kon may problema ka sa pagtuon?",
            "Ano ang imo himuon kon may duha ka assignment kag isa lang ka oras?",
            "Ipaathag kon paano ka magdesisyon kon may problema.",
        ],
        "english": [
            "What is 12 + 15? Explain how you worked it out.",
            "What is 45 - 19? Explain how you solved it.",
            "What is 8 x 7? Explain how you solved it.",
            "What is 64 / 8? Explain how you solved it.",
            "Why is education important to you?",
            "Explain how you prepare for an exam.",
            "What do you do when you have difficulty studying?",
            "What would you do if you had two assignments and only one hour?",
            "Explain how you make a decision when you face a problem.",
        ],
    },
    "Intensive": {
        "hiligaynon": [
            "Paano mo masolbar ang 25 x 18? Ipaathag ang mga tikang.",
            "Kon may PhP 500 ka, paano mo ini i-budget para sa isa ka semana?",
            "Kon may tatlo ka ka-deadline sa isa ka adlaw, paano mo ini i-manage?",
            "Ipaathag ang proseso sang paghimo sang project halin sa umpisa tubtob matapos.",
            "Ano ang mahimo matabo kon indi ka magtuon para sa exam? Ipaathag ang imo pag-analisar.",
            "Ihambal ang kinatuhayan sang maayo nga estudyante kag sang estudyante nga wala nagapanikasog.",
            "Kon ikaw ang teacher, paano mo tudluan ang estudyante nga budlay makaintindi?",
            "Ngaa importante ang critical thinking para sa estudyante?",
        ],
        "english": [
            "How would you solve 25 x 18? Explain each step.",
            "If you had PhP 500, how would you budget it for one week?",
            "If you had three deadlines on the same day, how would you manage them?",
            "Explain the steps for completing a project from beginning to end.",
            "What could happen if you did not study for an exam? Analyze the situation.",
            "Compare a diligent student with a student who does not make an effort.",
            "If you were a teacher, how would you teach a student who has difficulty understanding?",
            "Why is critical thinking important for a student?",
        ],
    },
}


def persist_language_choice():
    key = f"language_selector_{st.session_state.session_id}"
    st.session_state.language = st.session_state[key]
    st.session_state.screening_errors = []


def continue_to_consent():
    st.session_state.current_step = 1


def accept_consent():
    if st.session_state.consent_accepted:
        st.session_state.current_step = 2


def persist_fatigue_rating():
    task_level = TASK_LEVELS[st.session_state.task_index]
    key = f"fatigue_rating_{st.session_state.session_id}_{task_level}"
    rating = st.session_state[key]
    if rating is not None:
        ratings = dict(st.session_state.task_ratings)
        ratings[task_level] = rating
        st.session_state.task_ratings = ratings
        st.session_state.samn_perelli_rating = rating


def persist_birthplace_province():
    key = f"birthplace_province_{st.session_state.session_id}"
    st.session_state.birthplace_province_code = st.session_state[key]
    st.session_state.birthplace = ""
    locality_key = f"birthplace_locality_{st.session_state.session_id}_{st.session_state.birthplace_province_code}"
    st.session_state[locality_key] = None


def persist_birthplace_locality():
    suffix = "philippines" if st.session_state.birthplace_scope == "philippines" else st.session_state.birthplace_province_code
    locality_key = f"birthplace_locality_{st.session_state.session_id}_{suffix}"
    st.session_state.birthplace = st.session_state.get(locality_key, "")


def persist_birthplace_scope():
    key = f"birthplace_scope_{st.session_state.session_id}"
    st.session_state.birthplace_scope = st.session_state[key]
    st.session_state.birthplace = ""
    st.session_state.birthplace_needs_review = False


def persist_manual_birthplace():
    key = f"birthplace_manual_{st.session_state.session_id}"
    st.session_state.birthplace_manual_text = st.session_state[key].strip()
    st.session_state.birthplace = st.session_state.birthplace_manual_text
    st.session_state.birthplace_needs_review = bool(st.session_state.birthplace)


def persist_native_language():
    key = f"native_language_{st.session_state.session_id}"
    st.session_state.native_language = st.session_state[key]


@st.cache_data(ttl=86400, show_spinner=False)
def load_province_localities(province_code):
    if province_code not in WESTERN_VISAYAS_PROVINCES:
        raise ValueError("Unsupported province code")

    url = f"https://psgc.gitlab.io/api/provinces/{province_code}/cities-municipalities/"
    with urlopen(url, timeout=8) as response:
        places = json.loads(response.read().decode("utf-8"))

    if not isinstance(places, list) or not places:
        raise ValueError("The official locality list was empty or invalid")

    province_name = WESTERN_VISAYAS_PROVINCES[province_code]
    return _format_locality_options(places, {province_code: province_name})


def _format_locality_options(places, province_names):
    options = []
    for place in places:
        name = place.get("name", "")
        if place.get("isCity") and name.startswith("City of "):
            name = f"{name.removeprefix('City of ')} City"
        elif place.get("isCity") and not name.endswith("City"):
            name = f"{name} City"
        province_name = province_names.get(place.get("provinceCode"), "Philippines")
        options.append(f"{name}, {province_name}")
    return sorted(set(options))


@st.cache_data(ttl=86400, show_spinner=False)
def load_all_ph_localities():
    with urlopen("https://psgc.gitlab.io/api/cities-municipalities/", timeout=12) as response:
        places = json.loads(response.read().decode("utf-8"))
    with urlopen("https://psgc.gitlab.io/api/provinces/", timeout=12) as response:
        provinces = json.loads(response.read().decode("utf-8"))
    if not isinstance(places, list) or not places or not isinstance(provinces, list):
        raise ValueError("The official Philippine locality list was invalid")
    province_names = {province["code"]: province["name"] for province in provinces}
    return _format_locality_options(places, province_names)


def submit_screening():
    language = st.session_state.language
    messages = SCREENING_TEXT[language]
    errors = []
    birthplace = st.session_state.birthplace.strip()

    if not birthplace:
        errors.append(messages["required_manual_birthplace"] if st.session_state.birthplace_scope == "outside_ph" else messages["required_birthplace"])
    elif st.session_state.birthplace_scope == "western_visayas" and not st.session_state.birthplace_needs_review:
        try:
            allowed_birthplaces = load_province_localities(st.session_state.birthplace_province_code)
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            allowed_birthplaces = []
            errors.append(messages["birthplace_unavailable"])
        if allowed_birthplaces and birthplace not in allowed_birthplaces:
            errors.append(messages["invalid_birthplace"])
    elif st.session_state.birthplace_scope == "philippines" and not st.session_state.birthplace_needs_review:
        try:
            allowed_birthplaces = load_all_ph_localities()
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            allowed_birthplaces = []
            errors.append(messages["birthplace_unavailable"])
        if allowed_birthplaces and birthplace not in allowed_birthplaces:
            errors.append(messages["invalid_birthplace"])
    else:
        valid_manual_location = (
            2 <= len(birthplace) <= 120
            and any(character.isalpha() for character in birthplace)
            and all(character.isalpha() or character in " .,'’()/-" for character in birthplace)
        )
        if not valid_manual_location:
            errors.append(messages["invalid_birthplace"])
        else:
            st.session_state.birthplace_needs_review = True

    native_language = st.session_state.native_language
    if native_language is None:
        errors.append(messages["required_native"])
    elif native_language != "Hiligaynon":
        errors.append(messages["ineligible"])

    st.session_state.screening_errors = errors
    if not errors:
        try:
            save_respondent(
                respondent_id=st.session_state.respondent_id,
                birthplace=birthplace,
                native_lang=native_language,
                freq_score=int(st.session_state.hiligaynon_frequency_score),
            )
        except Exception as exc:
            st.session_state.persistence_error = str(exc)
            st.session_state.screening_errors = [
                "We could not save your screening details. Check the connection and try again."
            ]
            return

        st.session_state.persistence_error = None
        st.session_state.current_task_level = TASK_LEVELS[0]
        st.session_state.task_index = 0
        st.session_state.recorded_audio_bytes = None
        st.session_state.task_recordings = {}
        st.session_state.task_ratings = {}
        st.session_state.current_step = 3


def previous_step():
    step = st.session_state.current_step
    if step == 1:
        st.session_state.current_step = 0
    elif step == 2:
        st.session_state.current_step = 1
    elif step == 3 and st.session_state.task_index > 0:
        st.session_state.task_index -= 1
        st.session_state.current_task_level = TASK_LEVELS[st.session_state.task_index]
        st.session_state.recorded_audio_bytes = st.session_state.task_recordings.get(st.session_state.current_task_level)
    elif step == 3:
        st.session_state.current_step = 2
    elif step == 4:
        st.session_state.current_step = 3


def persist_consent():
    key = f"consent_check_{st.session_state.session_id}"
    st.session_state.consent_accepted = st.session_state[key]


def open_rating_step():
    task_level = TASK_LEVELS[st.session_state.task_index]
    if st.session_state.task_recordings.get(task_level):
        st.session_state.current_step = 4


def save_rating_and_continue():
    task_level = TASK_LEVELS[st.session_state.task_index]
    if task_level not in st.session_state.task_ratings:
        return
    if st.session_state.task_index < len(TASK_LEVELS) - 1:
        st.session_state.task_index += 1
        st.session_state.current_task_level = TASK_LEVELS[st.session_state.task_index]
        st.session_state.recorded_audio_bytes = st.session_state.task_recordings.get(st.session_state.current_task_level)
        st.session_state.current_step = 3
    else:
        pending_tasks = [
            task for task in TASK_LEVELS
            if task not in st.session_state.ingested_tasks
        ]
        try:
            for task in pending_tasks:
                audio_bytes = st.session_state.task_recordings.get(task)
                rating = st.session_state.task_ratings.get(task)
                if not audio_bytes or rating is None:
                    raise ValueError(f"Task {task} is missing its recording or fatigue rating.")

                wav_bytes = standardize_audio(audio_bytes)
                filename = (
                    f"{st.session_state.respondent_id}/"
                    f"{st.session_state.session_id}/{task.lower()}.wav"
                )
                audio_url = upload_audio_blob(wav_bytes, filename)
                log_session(
                    respondent_id=st.session_state.respondent_id,
                    task_level=task,
                    ground_truth=int(rating),
                    audio_url=audio_url,
                    session_id=st.session_state.session_id,
                )
                ingested = dict(st.session_state.ingested_tasks)
                ingested[task] = audio_url
                st.session_state.ingested_tasks = ingested
        except Exception as exc:
            st.session_state.persistence_error = str(exc)
            return

        st.session_state.persistence_error = None
        st.session_state.current_step = 5


def finish_debrief():
    if st.session_state.post_debrief_choice == "decline":
        purge_withdrawn_participant(destination_step=8)
    elif st.session_state.post_debrief_choice == "agree":
        st.session_state.current_step = 6


def clear_participant_data(destination_step):
    st.session_state.task_recordings = {}
    st.session_state.task_ratings = {}
    st.session_state.ingested_tasks = {}
    st.session_state.recorded_audio_bytes = None
    st.session_state.inference_results = {}
    st.session_state.persistence_error = None
    st.session_state.pending_cloud_purge = None
    st.session_state.cloud_purge_error = None
    st.session_state.respondent_id = f"WVSU-{uuid.uuid4().hex}"
    st.session_state.birthplace = ""
    st.session_state.birthplace_manual_text = ""
    st.session_state.birthplace_scope = "western_visayas"
    st.session_state.birthplace_province_code = "063000000"
    st.session_state.birthplace_needs_review = False
    st.session_state.native_language = None
    st.session_state.hiligaynon_frequency_score = 3
    st.session_state.samn_perelli_rating = None
    st.session_state.current_task_level = TASK_LEVELS[0]
    st.session_state.task_index = 0
    st.session_state.screening_errors = []
    st.session_state.consent_accepted = False
    st.session_state.post_debrief_choice = None
    st.session_state.post_debrief_consent = False
    st.session_state.persistence_error = None
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.current_step = destination_step


def withdraw_session():
    purge_withdrawn_participant(destination_step=7)


def retry_cloud_purge():
    purge_withdrawn_participant(destination_step=st.session_state.current_step)


def purge_withdrawn_participant(destination_step):
    pending = st.session_state.get("pending_cloud_purge")
    if pending is None:
        pending = {
            "respondent_id": st.session_state.respondent_id,
            "session_id": st.session_state.session_id,
        }
        st.session_state.pending_cloud_purge = pending

    try:
        delete_participant_data(
            respondent_id=pending["respondent_id"],
            session_id=pending["session_id"],
        )
    except Exception as exc:
        st.session_state.cloud_purge_error = str(exc)
        purge_error = str(exc)
        purge_session_state(st.session_state, destination_step=destination_step)
        st.session_state.pending_cloud_purge = pending
        st.session_state.cloud_purge_error = purge_error
        return

    st.session_state.cloud_purge_error = None
    st.session_state.pending_cloud_purge = None
    purge_session_state(st.session_state, destination_step=destination_step)


def persist_post_debrief_choice():
    st.session_state.post_debrief_choice = st.session_state[f"post_debrief_choice_{st.session_state.session_id}"]
    if st.session_state.post_debrief_choice == "decline":
        purge_withdrawn_participant(destination_step=8)


def render_study_banner(title, subtitle):
    st.markdown(
        f"""
        <div class="study-banner">
            <div class="study-banner-tag">Study workflow</div>
            <div class="study-banner-title">{title}</div>
            <div class="study-banner-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_progress(text):
    step = st.session_state.current_step
    labels = text["progress"]
    progress_value = {1: 0.2, 2: 0.4, 3: 0.6, 4: 0.8, 5: 1.0, 6: 1.0}.get(step)
    if progress_value is not None:
        st.progress(progress_value)
        st.caption("  ›  ".join(labels[1:]))
    if step in (1, 2, 3, 4, 5):
        with st.expander(text["withdraw"], expanded=False):
            st.warning(text["withdraw_body"])
            st.button(
                text["withdraw"],
                key=f"withdraw_{st.session_state.session_id}",
                on_click=withdraw_session,
                type="secondary",
            )
    if st.session_state.get("cloud_purge_error"):
        st.error(
            "Your local session has been cleared, but cloud deletion has not yet completed. "
            "Reconnect to the database and retry the deletion below."
        )
    if st.session_state.get("persistence_error"):
        st.error(
            "Data could not be saved to the research database. Please check the connection and retry."
        )


def render_language_step(text):
    render_study_banner(text["app_title"], text["language_intro"])
    st.subheader(text["language_title"])
    st.write(text["language_intro"])
    language_key = f"language_selector_{st.session_state.session_id}"
    st.radio(
        text["language_label"],
        options=LANGUAGES,
        horizontal=True,
        key=language_key,
        index=LANGUAGES.index(st.session_state.language),
        on_change=persist_language_choice,
    )
    st.button(text["language_continue"], type="primary", on_click=continue_to_consent)


def render_consent_step(text):
    consent_text = CONSENT_TEXT[st.session_state.language]
    render_study_banner(text["consent_title"], consent_text["purpose"][:110] + ("..." if len(consent_text["purpose"]) > 110 else ""))
    render_progress(text)
    st.subheader(consent_text["purpose_title"])
    st.write(consent_text["purpose"])
    st.subheader(consent_text["participation_title"])
    st.write(consent_text["participation"])
    st.subheader(consent_text["privacy_title"])
    st.write(consent_text["privacy"])
    st.subheader(consent_text["withdraw_title"])
    st.write(consent_text["withdraw"])
    st.caption(text["consent_notice"])
    st.checkbox(
        text["consent_ack"],
        key=f"consent_check_{st.session_state.session_id}",
        value=st.session_state.consent_accepted,
        on_change=persist_consent,
    )
    st.button(
        text["consent_next"],
        type="primary",
        disabled=not st.session_state.consent_accepted,
        on_click=accept_consent,
    )


def render_screening_step():
    language = st.session_state.language
    text = SCREENING_TEXT[language]
    render_study_banner(text["step"], text["intro"])
    render_progress(FLOW_TEXT[language])
    session_id = st.session_state.session_id
    language_key = f"language_selector_{session_id}"
    st.radio(
        text["language"],
        options=LANGUAGES,
        format_func=lambda value: {"Hiligaynon": "Hiligaynon", "English": "English"}[value],
        index=LANGUAGES.index(st.session_state.language),
        horizontal=True,
        key=language_key,
        on_change=persist_language_choice,
    )
    st.caption(f"{text['respondent_id']}: {st.session_state.respondent_id}")
    st.markdown(f"**{text['birthplace']}**")
    scope_options = ["western_visayas", "philippines", "outside_ph"]
    scope_key = f"birthplace_scope_{session_id}"
    st.selectbox(
        text["birthplace_scope"],
        options=scope_options,
        format_func=lambda scope: text["birthplace_scopes"][scope],
        index=scope_options.index(st.session_state.birthplace_scope),
        key=scope_key,
        on_change=persist_birthplace_scope,
    )
    birthplace_options = []
    birthplace_available = True
    if st.session_state.birthplace_scope == "western_visayas":
        province_codes = list(WESTERN_VISAYAS_PROVINCES)
        province_key = f"birthplace_province_{session_id}"
        province_code = st.selectbox(
            text["birthplace_province"],
            options=province_codes,
            format_func=lambda code: WESTERN_VISAYAS_PROVINCES[code],
            index=province_codes.index(st.session_state.birthplace_province_code),
            key=province_key,
            on_change=persist_birthplace_province,
        )
        st.session_state.birthplace_province_code = province_code
        try:
            birthplace_options = load_province_localities(province_code)
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            birthplace_available = False
    elif st.session_state.birthplace_scope == "philippines":
        try:
            birthplace_options = load_all_ph_localities()
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            birthplace_available = False

    if st.session_state.birthplace_scope != "outside_ph":
        if not birthplace_available:
            st.warning(text["birthplace_fallback"])
            manual_key = f"birthplace_manual_{session_id}"
            st.text_input(
                text["birthplace_manual"],
                value=st.session_state.birthplace_manual_text,
                max_chars=120,
                key=manual_key,
                on_change=persist_manual_birthplace,
            )
        else:
            locality_key = f"birthplace_locality_{session_id}_{st.session_state.birthplace_province_code}"
            if st.session_state.birthplace_scope == "philippines":
                locality_key = f"birthplace_locality_{session_id}_philippines"
            selected_birthplace = st.session_state.birthplace if st.session_state.birthplace in birthplace_options else None
            st.selectbox(
                text["birthplace_locality"],
                options=birthplace_options,
                index=birthplace_options.index(selected_birthplace) if selected_birthplace else None,
                key=locality_key,
                on_change=persist_birthplace_locality,
                disabled=not birthplace_options,
            )
    else:
        manual_key = f"birthplace_manual_{session_id}"
        st.text_input(
            text["birthplace_manual"],
            value=st.session_state.birthplace_manual_text,
            max_chars=120,
            key=manual_key,
            on_change=persist_manual_birthplace,
        )
        if st.session_state.birthplace_manual_text:
            st.info(FLOW_TEXT[language]["manual_birthplace_notice"])

    native_key = f"native_language_{session_id}"
    st.selectbox(
        text["native_language"],
        options=NATIVE_LANGUAGES,
        index=NATIVE_LANGUAGES.index(st.session_state.native_language) if st.session_state.native_language else None,
        format_func=lambda value: text["native_names"][value],
        key=native_key,
        on_change=persist_native_language,
    )
    st.markdown("### Hiligaynon")
    frequency_key = f"frequency_score_{session_id}"
    frequency = st.session_state.hiligaynon_frequency_score
    st.markdown(
        f"""
        <div style="
            font-size:1.05rem;
            font-weight:600;
            color:#0f172a;
            margin-bottom:0.8rem;
        ">
            {text['frequency']}
        </div>
        """,
        unsafe_allow_html=True,
    )
    frequency_labels = FLOW_TEXT[language]["frequency_values"]
    frequency_options = {
        1: frequency_labels[0],
        2: frequency_labels[1],
        3: frequency_labels[2],
        4: frequency_labels[3],
        5: frequency_labels[4],
    }

    selected_frequency = st.radio(
        "Select one:",
        options=list(frequency_options),
        format_func=lambda value: f"{value} — {frequency_options[value]}",
        index=int(frequency if frequency in [1, 2, 3, 4, 5] else 3) - 1,
        key=f"{frequency_key}_radio",
        horizontal=True,
    )
    st.session_state.hiligaynon_frequency_score = selected_frequency
    st.session_state[frequency_key] = selected_frequency
    st.caption(text["frequency_selected"].format(value=selected_frequency, anchor=frequency_labels[selected_frequency - 1]))

    for error in st.session_state.screening_errors:
        st.error(error)

    previous_col, next_col = st.columns(2)
    with previous_col:
        st.button(text["previous"], on_click=previous_step, width="stretch")
    with next_col:
        if st.button(
            text["next"],
            type="primary",
            width="stretch",
            disabled=(
                not birthplace_available
                and not st.session_state.birthplace_manual_text.strip()
            ),
        ):
            with st.spinner("Saving participant screening details..."):
                submit_screening()
            if st.session_state.current_step == 3:
                st.rerun()


def render_task_step():
    language = st.session_state.language
    text = UI_TEXT[language]
    screening = SCREENING_TEXT[language]
    flow = FLOW_TEXT[language]
    task_level = TASK_LEVELS[st.session_state.task_index]
    render_study_banner(text["step_task"], f"{flow['task_order'].format(part=chr(ord('A') + st.session_state.task_index), number=st.session_state.task_index + 1, task=text['task_names'][task_level])}")
    render_progress(flow)
    part_letter = chr(ord("A") + st.session_state.task_index)
    st.caption(
        flow["task_order"].format(
            part=part_letter,
            number=st.session_state.task_index + 1,
            task=text["task_names"][task_level],
        )
    )
    prompt = TASK_PROMPTS[task_level]
    st.info(text["task_instructions"])
    for question_number, question in enumerate(prompt[language.lower()], start=1):
        st.markdown(f"**{text['prompt_label']} {question_number}:** {question}")
    st.caption(text["draft_notice"])

    audio_key = f"participant_audio_{st.session_state.session_id}_{task_level}"
    uploaded = st.file_uploader(
        flow["upload_title"],
        type=["wav", "mp3", "m4a", "ogg"],
        help=flow["upload_help"],
        key=audio_key,
    )

    if uploaded is not None:
        with st.spinner(text["upload_processing"]):
            audio_bytes = uploaded.getvalue()
            if audio_bytes:
                recordings = dict(st.session_state.task_recordings)
                recordings[task_level] = audio_bytes
                st.session_state.task_recordings = recordings
                st.session_state.recorded_audio_bytes = audio_bytes
            else:
                recordings = dict(st.session_state.task_recordings)
                recordings.pop(task_level, None)
                st.session_state.task_recordings = recordings
                st.session_state.recorded_audio_bytes = None
        if audio_bytes:
            st.audio(audio_bytes)
            st.success(text["audio_ready"])
        else:
            st.error(text["audio_error"])
    if st.session_state.recorded_audio_bytes:
        st.success(flow["task_complete"])
    else:
        st.info(text["audio_required"])

    col1, col2 = st.columns([1, 1])
    with col1:
        st.button(screening["previous"], width="stretch", on_click=previous_step)
    with col2:
        st.button(
            flow["next_rating"],
            type="primary",
            width="stretch",
            disabled=not st.session_state.task_recordings.get(task_level),
            on_click=open_rating_step,
        )


def render_rating_step():
    language = st.session_state.language
    text = UI_TEXT[language]
    screening = SCREENING_TEXT[language]
    flow = FLOW_TEXT[language]
    task_level = TASK_LEVELS[st.session_state.task_index]
    render_study_banner(text["step_rating"], text["rating_intro"])
    render_progress(flow)
    st.caption(flow["rating_order"].format(number=st.session_state.task_index + 1))
    st.write(text["rating_intro"])

    rating_key = f"fatigue_rating_{st.session_state.session_id}_{task_level}"
    stored_rating = st.session_state.task_ratings.get(task_level)
    rating = st.radio(
        text["rating_prompt"],
        options=SAMN_SCALE,
        format_func=lambda value: f"{value} · {SAMN_LABELS[language][value - 1]}",
        horizontal=False,
        index=None if stored_rating is None else SAMN_SCALE.index(stored_rating),
        key=rating_key,
        on_change=persist_fatigue_rating,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        st.button(screening["previous"], width="stretch", on_click=previous_step)
    with col2:
        if st.button(
            flow["finish_tasks"] if st.session_state.task_index == len(TASK_LEVELS) - 1 else flow["next_task"],
            type="primary",
            width="stretch",
            disabled=rating is None,
        ):
            if st.session_state.task_index == len(TASK_LEVELS) - 1:
                with st.spinner("Standardizing and uploading all task recordings..."):
                    save_rating_and_continue()
            else:
                save_rating_and_continue()
            if st.session_state.get("persistence_error"):
                st.error(
                    "We could not save the task data to the research database. "
                    "Check the connection and retry."
                )
            else:
                st.rerun()


def render_debriefing_step():
    language = st.session_state.language
    text = UI_TEXT[language]
    flow = FLOW_TEXT[language]
    render_study_banner(text["step_debrief"], text["thanks"])
    render_progress(flow)
    st.success(text["thanks"])
    st.subheader(text["disclosure_title"])
    st.write(text["disclosure"])
    st.write(text["withdrawal"])
    st.caption(f"{text['participant_code']}: {st.session_state.respondent_id}")
    st.subheader(text["task_label"])
    for task_level in TASK_LEVELS:
        task_name = text["task_names"][task_level]
        recording = flow["recording_present"] if st.session_state.task_recordings.get(task_level) else flow["recording_missing"]
        rating = st.session_state.task_ratings.get(task_level)
        rating_label = f"{rating} · {SAMN_LABELS[language][rating - 1]}" if rating is not None else text["no_rating"]
        st.write(f"{task_name} · {text['recording_label']}: {recording} · {text['rating_label']}: {rating_label}")
    if st.session_state.birthplace_needs_review:
        st.warning(flow["manual_birthplace_notice"])
    st.subheader(flow["post_consent_prompt"])
    choice_key = f"post_debrief_choice_{st.session_state.session_id}"
    choice = st.radio(
        text["post_consent"],
        options=["agree", "decline"],
        format_func=lambda value: flow["post_consent_options"][value],
        index=None if st.session_state.post_debrief_choice is None else ["agree", "decline"].index(st.session_state.post_debrief_choice),
        key=choice_key,
        on_change=persist_post_debrief_choice,
        label_visibility="collapsed",
    )
    if choice is not None:
        st.info(text["post_consent_yes"] if choice == "agree" else flow["post_consent_options"]["decline"] + ". " + text["post_consent_no"])
    st.button(
        flow["finish_debrief"],
        type="primary",
        on_click=finish_debrief,
        disabled=st.session_state.post_debrief_choice is None,
    )


def reset_session():
    clear_participant_data(0)
    st.session_state.birthplace_scope = "western_visayas"
    st.session_state.birthplace_province_code = "063000000"


language_text = FLOW_TEXT[st.session_state.language]
if st.session_state.current_step == 0:
    render_language_step(language_text)
elif st.session_state.current_step == 1:
    render_consent_step(language_text)
elif st.session_state.current_step == 2:
    render_screening_step()
elif st.session_state.current_step == 3:
    render_task_step()
elif st.session_state.current_step == 4:
    render_rating_step()
elif st.session_state.current_step == 5:
    render_debriefing_step()
elif st.session_state.current_step == 6:
    st.title(language_text["complete_title"])
    st.success(language_text["complete_body"])
    st.button(language_text["reset"], type="primary", on_click=reset_session)
elif st.session_state.current_step == 7:
    st.title(language_text["withdraw_title"])
    st.success(language_text["withdraw_body"])
    if st.session_state.get("cloud_purge_error"):
        st.error("Cloud deletion is pending. Your local session has been cleared.")
        st.button("Retry cloud deletion", on_click=retry_cloud_purge)
    st.button(language_text["reset"], type="primary", on_click=reset_session)
elif st.session_state.current_step == 8:
    st.title(language_text["declined_title"])
    st.success(language_text["declined_body"])
    if st.session_state.get("cloud_purge_error"):
        st.error("Cloud deletion is pending. Your local session has been cleared.")
        st.button("Retry cloud deletion", on_click=retry_cloud_purge)
    st.button(language_text["reset"], type="primary", on_click=reset_session)
