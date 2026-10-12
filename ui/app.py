"""
ui/app.py
──────────
Streamlit dashboard for the AI Meeting-to-Action Pipeline.

Features:
  - Audio file upload or transcript paste mode
  - Sample transcript loader for quick demos
  - Results table with priority color-coding
  - Notion + Slack dispatch status
  - JSON download of extracted action items
  - Real-time backend health indicator

Run:
  streamlit run ui/app.py
"""

import json
import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Meeting Action Engine",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — Premium dark theme
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Main background */
    .stApp {
        background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
        min-height: 100vh;
    }

    /* Hero header */
    .hero-header {
        text-align: center;
        padding: 2rem 0 1rem 0;
    }
    .hero-title {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea, #764ba2, #f093fb);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.3rem;
    }
    .hero-subtitle {
        color: #8b9dc3;
        font-size: 1.1rem;
        font-weight: 400;
    }

    /* Cards */
    .metric-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 1.2rem;
        text-align: center;
        backdrop-filter: blur(10px);
    }
    .metric-number {
        font-size: 2rem;
        font-weight: 700;
        color: #667eea;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #8b9dc3;
        margin-top: 0.2rem;
    }

    /* Status badges */
    .badge-critical { color: #ff6b6b; font-weight: 700; }
    .badge-high     { color: #ffd93d; font-weight: 700; }
    .badge-medium   { color: #6bcb77; font-weight: 700; }
    .badge-low      { color: #adb5bd; font-weight: 700; }

    /* Section headers */
    .section-header {
        font-size: 1.2rem;
        font-weight: 600;
        color: #c5d0e6;
        border-bottom: 1px solid rgba(102,126,234,0.3);
        padding-bottom: 0.4rem;
        margin-bottom: 1rem;
    }

    /* Sidebar styling */
    .css-1d391kg, [data-testid="stSidebar"] {
        background: rgba(15,15,26,0.8) !important;
    }

    /* Primary button */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #667eea, #764ba2);
        border: none;
        color: white;
        font-weight: 600;
        border-radius: 10px;
        padding: 0.6rem 1.5rem;
        transition: all 0.3s ease;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(102,126,234,0.4);
    }

    /* Pipeline flow indicator */
    .pipeline-step {
        display: inline-block;
        background: rgba(102,126,234,0.15);
        border: 1px solid rgba(102,126,234,0.3);
        border-radius: 8px;
        padding: 0.3rem 0.8rem;
        font-size: 0.8rem;
        color: #667eea;
        margin: 0.2rem;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sample Transcript
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = """Alright team, let's recap action items from today's sprint planning.

Shubham, you need to complete the API integration for the payment module by July 25th, 2026. 
This is blocking the QA team from starting their testing.

Vijay, please make sure all unit tests are passing before the QA handoff on July 28th. 
The staging environment needs to be clean.

Priya will set up the staging environment by EOD tomorrow — this is critical because 
the client demo is scheduled for next week.

We should also schedule a follow-up sync next Monday — Ravi, can you send the calendar invite 
to the whole team?

Also, someone needs to update the README with the new deployment steps. 
Shubham, can you do that by end of this week?

The marketing team asked for a feature demo video. We haven't assigned an owner yet for that."""


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def check_backend_health() -> bool:
    """Ping backend health endpoint."""
    try:
        r = requests.get(f"{BACKEND_URL}/api/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def priority_color(label: str) -> str:
    """Return an HTML-colored priority badge."""
    colors = {
        "Critical": "#ff6b6b",
        "High": "#ffd93d",
        "Medium": "#6bcb77",
        "Low": "#adb5bd",
    }
    emojis = {"Critical": "🔴", "High": "🟡", "Medium": "🟢", "Low": "⚪"}
    color = colors.get(label, "#8b9dc3")
    emoji = emojis.get(label, "⚫")
    return f'<span style="color:{color};font-weight:700">{emoji} {label}</span>'


def render_priority_table(actions: list):
    """Render a styled dataframe of action items."""
    if not actions:
        st.info("No action items found in this transcript.")
        return

    df = pd.DataFrame(actions)
    display_cols = {
        "task": "📋 Task",
        "owner": "👤 Owner",
        "deadline": "📅 Deadline",
        "priority_label": "⚡ Priority",
        "priority_score": "Score",
        "confidence": "🎯 Confidence",
        "needs_review": "⚠️ Review?",
    }

    available = {k: v for k, v in display_cols.items() if k in df.columns}
    display_df = df[list(available.keys())].rename(columns=available)

    # Format confidence as percentage
    if "🎯 Confidence" in display_df.columns:
        display_df["🎯 Confidence"] = display_df["🎯 Confidence"].apply(
            lambda x: f"{float(x)*100:.0f}%"
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Hero Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero-header">
    <div class="hero-title">🤖 AI Meeting Action Engine</div>
    <div class="hero-subtitle">
        Transform meeting recordings into structured action items — dispatched to Notion & Slack automatically
    </div>
</div>
""", unsafe_allow_html=True)

# Pipeline flow indicator
st.markdown("""
<div style="text-align:center; margin-bottom: 1.5rem;">
    <span class="pipeline-step">🎙️ Audio/Text</span>
    <span style="color:#667eea;margin:0 0.3rem">→</span>
    <span class="pipeline-step">🔍 Extract</span>
    <span style="color:#667eea;margin:0 0.3rem">→</span>
    <span class="pipeline-step">⚡ Prioritize</span>
    <span style="color:#667eea;margin:0 0.3rem">→</span>
    <span class="pipeline-step">✅ Format</span>
    <span style="color:#667eea;margin:0 0.3rem">→</span>
    <span class="pipeline-step">📋 Notion</span>
    <span style="color:#667eea;margin:0 0.3rem">+</span>
    <span class="pipeline-step">💬 Slack</span>
</div>
""", unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ Settings")

    # Backend health check
    is_healthy = check_backend_health()
    if is_healthy:
        st.success("✅ Backend connected")
    else:
        st.error("❌ Backend unreachable")
        st.caption(f"Expected at: `{BACKEND_URL}`")
        st.caption("Run: `uvicorn api.main:app --reload --port 8000`")

    st.divider()

    st.markdown("### 🔌 Integrations")
    send_to_notion = st.checkbox("📋 Dispatch to Notion", value=True)
    send_to_slack = st.checkbox("💬 Send to Slack", value=True)

    if not send_to_notion and not send_to_slack:
        st.warning("Both integrations disabled — results still shown on screen.")

    st.divider()

    st.markdown("### ℹ️ About")
    st.markdown("""
    **AI Meeting-to-Action Pipeline**
    
    - 🎙️ Whisper API transcription
    - 🤖 Groq LLM extraction
    - ⚡ Priority scoring (1-25)
    - 📋 Notion task creation
    - 💬 Slack notifications
    - ❌ Zero GPU required
    """)

    st.markdown("---")
    st.caption("v1.0.0 · Built with LangGraph")

# ─────────────────────────────────────────────────────────────────────────────
# Main Layout
# ─────────────────────────────────────────────────────────────────────────────

left_col, right_col = st.columns([1, 1], gap="large")

# ── Left column: Input ──────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="section-header">📥 Input</div>', unsafe_allow_html=True)

    input_mode = st.radio(
        "Choose input mode:",
        ["🎙️ Audio File Upload", "📝 Transcript Paste"],
        horizontal=True,
    )

    uploaded_file = None
    text_input = ""

    if input_mode == "🎙️ Audio File Upload":
        st.markdown("""
        <div style='background:rgba(102,126,234,0.08);border:1px solid rgba(102,126,234,0.2);
        border-radius:10px;padding:0.8rem;margin-bottom:1rem;font-size:0.85rem;color:#8b9dc3;'>
        ℹ️ Max 25 MB · Supported: mp3, wav, m4a, ogg, webm<br>
        Your file is transcribed via <strong>Groq Whisper API</strong> — no GPU needed.
        </div>
        """, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            "Upload meeting recording",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            label_visibility="collapsed",
        )

        if uploaded_file:
            st.audio(uploaded_file, format=f"audio/{uploaded_file.name.split('.')[-1]}")
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.caption(f"📁 {uploaded_file.name} · {file_size_mb:.1f} MB")

    else:
        # Sample transcript loader
        if st.button("📋 Load Sample Transcript", use_container_width=True):
            st.session_state["loaded_transcript"] = SAMPLE_TRANSCRIPT

        text_input = st.text_area(
            "Paste meeting transcript here:",
            value=st.session_state.get("loaded_transcript", ""),
            height=350,
            placeholder=(
                "Example:\n"
                "Shubham will complete the API integration by July 25th.\n"
                "Vijay needs to write unit tests before QA handoff on July 28th.\n"
                "Priya will set up staging by EOD tomorrow..."
            ),
            label_visibility="collapsed",
        )

        if text_input:
            char_count = len(text_input)
            word_count = len(text_input.split())
            st.caption(f"📝 {word_count} words · {char_count} characters")

    # Process button
    st.markdown("<br>", unsafe_allow_html=True)
    has_input = bool(uploaded_file) or bool(text_input.strip())
    process_btn = st.button(
        "🚀 Run Pipeline",
        type="primary",
        disabled=not has_input or not is_healthy,
        use_container_width=True,
    )

    if not is_healthy:
        st.caption("⚠️ Backend must be running to process.")

# ── Right column: Results ────────────────────────────────────────────────────
with right_col:
    st.markdown('<div class="section-header">📊 Results</div>', unsafe_allow_html=True)

    if process_btn and has_input:
        with st.spinner("🔄 Processing... Transcription → Extraction → Prioritization → Dispatch"):
            try:
                response = None

                if input_mode == "🎙️ Audio File Upload" and uploaded_file:
                    uploaded_file.seek(0)
                    files = {
                        "audio_file": (
                            uploaded_file.name,
                            uploaded_file.read(),
                            f"audio/{uploaded_file.name.split('.')[-1]}",
                        )
                    }
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/pipeline/process",
                        files=files,
                        data={
                            "send_to_notion": send_to_notion,
                            "send_to_slack": send_to_slack,
                        },
                        timeout=300,  # long timeout for transcription + 3 LLM calls
                    )
                else:
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/pipeline/process",
                        data={
                            "raw_transcript": text_input,
                            "send_to_notion": send_to_notion,
                            "send_to_slack": send_to_slack,
                        },
                        timeout=120,
                    )

                if response and response.status_code == 200:
                    data = response.json()
                    actions = data.get("extracted_actions", [])
                    total = data.get("total_items", 0)
                    mcp = data.get("mcp_results", {})
                    errors = data.get("errors", [])

                    # ── Summary metrics ──────────────────────────────────────
                    st.markdown("#### 📈 Summary")
                    m1, m2, m3, m4 = st.columns(4)

                    critical_count = sum(1 for a in actions if a.get("priority_label") == "Critical")
                    high_count = sum(1 for a in actions if a.get("priority_label") == "High")
                    review_count = sum(1 for a in actions if a.get("needs_review"))

                    with m1:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number">{total}</div>
                            <div class="metric-label">Total Items</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m2:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#ff6b6b">{critical_count}</div>
                            <div class="metric-label">Critical</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m3:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#ffd93d">{high_count}</div>
                            <div class="metric-label">High Priority</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m4:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#f093fb">{review_count}</div>
                            <div class="metric-label">Need Review</div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    # ── Action Items Table ───────────────────────────────────
                    st.markdown("#### 📋 Extracted Action Items")
                    render_priority_table(actions)

                    if actions:
                        # Download button
                        st.download_button(
                            label="⬇️ Download as JSON",
                            data=json.dumps(actions, indent=2),
                            file_name="action_items.json",
                            mime="application/json",
                            use_container_width=True,
                        )

                    # ── Integration Status ───────────────────────────────────
                    st.markdown("#### 🔌 Integration Status")
                    n_col, s_col = st.columns(2)

                    with n_col:
                        notion = mcp.get("notion", {})
                        created = notion.get("created", 0)
                        n_total = notion.get("total", 0)
                        if notion.get("skipped"):
                            st.info("📋 Notion: disabled for this run")
                        elif notion.get("error") and "missing" in str(notion.get("error", "")):
                            st.warning(f"📋 Notion: credentials not set")
                        elif created > 0:
                            st.success(f"📋 Notion: {created}/{n_total} tasks created")
                        else:
                            err = notion.get("error", "Failed")
                            st.error(f"📋 Notion: {err}")

                    with s_col:
                        slack = mcp.get("slack", {})
                        if slack.get("skipped"):
                            st.info("💬 Slack: disabled for this run")
                        elif slack.get("success"):
                            sent = slack.get("items_sent", 0)
                            st.success(f"💬 Slack: {sent} items sent")
                        elif slack.get("error") and "missing" in str(slack.get("error", "")):
                            st.warning(f"💬 Slack: webhook not configured")
                        else:
                            st.error(f"💬 Slack: {slack.get('error', 'Failed')}")

                    # ── Transcript Preview ───────────────────────────────────
                    with st.expander("🔍 View Transcript Preview"):
                        st.text(data.get("transcript_preview", "N/A"))

                    # ── Errors (if any) ──────────────────────────────────────
                    if errors:
                        with st.expander(f"⚠️ Pipeline Warnings ({len(errors)})"):
                            for err in errors:
                                st.warning(err)

                else:
                    status_code = response.status_code if response else "N/A"
                    try:
                        detail = response.json().get("detail", "Unknown error")
                    except Exception:
                        detail = "Could not parse error response."
                    st.error(f"❌ Pipeline failed [{status_code}]: {detail}")

            except requests.exceptions.ConnectionError:
                st.error(
                    "❌ Cannot connect to backend. "
                    "Make sure FastAPI is running: `uvicorn api.main:app --reload --port 8000`"
                )
            except requests.exceptions.Timeout:
                st.error(
                    "⏱️ Request timed out. "
                    "Large audio files or complex transcripts may take longer."
                )
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")

    else:
        # Placeholder state
        st.markdown("""
        <div style='
            text-align: center;
            padding: 4rem 2rem;
            background: rgba(102,126,234,0.05);
            border: 1px dashed rgba(102,126,234,0.2);
            border-radius: 16px;
            color: #8b9dc3;
        '>
            <div style='font-size: 3rem; margin-bottom: 1rem'>🤖</div>
            <div style='font-size: 1.1rem; font-weight: 500; color: #c5d0e6; margin-bottom: 0.5rem'>
                Ready to extract action items
            </div>
            <div style='font-size: 0.9rem'>
                Upload an audio file or paste a transcript,<br>
                then click <strong>🚀 Run Pipeline</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
