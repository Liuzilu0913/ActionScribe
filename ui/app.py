"""
ui/app.py
──────────
Streamlit dashboard for the AI Meeting-to-Action Pipeline.

Features:
  - Audio file upload or transcript paste mode
  - Sample transcript loader for quick demos
  - Results table with priority color-coding
  - Feishu Bitable and group-notification status
  - JSON download of extracted action items
  - Real-time backend health indicator

Run:
  streamlit run ui/app.py
"""

import json
import os
from datetime import date

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ActionScribe · 会议行动项助手",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — Bright, clean theme
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    :root {
        --ink: #172033;
        --muted: #64748b;
        --blue: #3459c7;
        --blue-soft: #edf3ff;
        --line: #e2e8f0;
        --surface: #ffffff;
    }
    html, body, [class*="css"] {
        font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
        color: var(--ink);
    }
    .stApp {
        background: linear-gradient(135deg, #f8fbff 0%, #f2f6fc 55%, #f8faff 100%);
        min-height: 100vh;
    }
    [data-testid="stAppViewContainer"] { background: transparent; }
    [data-testid="stHeader"] { background: rgba(248, 251, 255, 0.88); }
    [data-testid="stMain"] { color: var(--ink); }

    /* Hero header */
    .hero-header {
        text-align: center;
        padding: 2rem 0 1.2rem 0;
    }
    .hero-title {
        font-size: 2.55rem;
        font-weight: 700;
        background: linear-gradient(120deg, #2446a8, #4277d4, #2796a8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.5rem;
    }
    .hero-subtitle {
        color: var(--muted);
        font-size: 1.1rem;
        font-weight: 400;
    }

    /* Cards */
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 5px 18px rgba(31, 51, 87, 0.055);
    }
    .metric-number {
        font-size: 2rem;
        font-weight: 700;
        color: var(--blue);
    }
    .metric-label {
        font-size: 0.85rem;
        color: var(--muted);
        margin-top: 0.2rem;
    }

    /* Status badges */
    .badge-critical { color: #b42318; font-weight: 700; }
    .badge-high     { color: #a15c00; font-weight: 700; }
    .badge-medium   { color: #18794e; font-weight: 700; }
    .badge-low      { color: #64748b; font-weight: 700; }

    /* Section headers */
    .section-header {
        font-size: 1.2rem;
        font-weight: 600;
        color: #25324a;
        border-bottom: 1px solid #dce6f4;
        padding-bottom: 0.4rem;
        margin-bottom: 1rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: #f6f8fc !important;
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] > div:first-child { background: transparent; }

    /* Primary button */
    .stButton > button[kind="primary"] {
        background: linear-gradient(120deg, #3459c7, #4778d2);
        border: none;
        color: white;
        font-weight: 600;
        border-radius: 9px;
        padding: 0.6rem 1.5rem;
        transition: all 0.3s ease;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(52, 89, 199, 0.22);
    }
    .stButton > button, .stDownloadButton > button { border-radius: 9px; }

    /* Pipeline flow indicator */
    .pipeline-step {
        display: inline-block;
        background: #ffffff;
        border: 1px solid #d9e4f4;
        border-radius: 8px;
        padding: 0.3rem 0.8rem;
        font-size: 0.8rem;
        color: #3459a9;
        margin: 0.2rem;
        box-shadow: 0 2px 7px rgba(31, 51, 87, 0.04);
    }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; }
    [data-testid="stTextArea"] textarea, [data-testid="stFileUploader"] {
        background-color: #ffffff;
    }

    /* Hide Streamlit branding while keeping its native sidebar toggle reachable. */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stAppDeployButton"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sample Transcript
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = """大家好，我们来回顾一下今天迭代规划会确定的待办事项。

张伟，请在 2026 年 7 月 25 日前完成支付模块的 API 联调。这项工作会影响 QA 团队开始测试。

李娜，请在 7 月 28 日交接给 QA 之前确认所有单元测试都已通过，并确保预发布环境正常。

王敏会在明天下班前搭建预发布环境。这项工作很紧急，因为客户演示安排在下周。

我们还需要在下周一安排一次跟进会议。陈浩，请把日历邀请发送给整个团队。

另外，需要更新 README 中的部署步骤。张伟，请在本周结束前完成。

市场团队还需要一段功能演示视频，目前还没有指定负责人。"""


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
    labels = {"Critical": "紧急", "High": "高", "Medium": "中", "Low": "低"}
    colors = {"Critical": "#b42318", "High": "#a15c00", "Medium": "#18794e", "Low": "#64748b"}
    emojis = {"Critical": "🔴", "High": "🟠", "Medium": "🟢", "Low": "⚪"}
    color = colors.get(label, "#64748b")
    emoji = emojis.get(label, "⚪")
    return f'<span style="color:{color};font-weight:700">{emoji} {labels.get(label, "待评估")}</span>'


def render_priority_table(actions: list):
    """Render a styled dataframe of action items."""
    if not actions:
        st.info("这段会议记录中没有识别到待办任务。")
        return

    df = pd.DataFrame(actions)
    display_cols = {
        "task": "📋 任务描述",
        "owner": "👤 负责人",
        "deadline": "📅 截止日期",
        "priority_label": "⚡ 优先级",
        "priority_score": "优先级分数",
        "confidence": "🎯 置信度",
        "needs_review": "⚠️ 复核状态",
    }

    available = {k: v for k, v in display_cols.items() if k in df.columns}
    display_df = df[list(available.keys())].rename(columns=available)

    if "⚡ 优先级" in display_df.columns:
        display_df["⚡ 优先级"] = display_df["⚡ 优先级"].map(
            {"Critical": "紧急", "High": "高", "Medium": "中", "Low": "低"}
        ).fillna("待评估")
    if "⚠️ 复核状态" in display_df.columns:
        display_df["⚠️ 复核状态"] = display_df["⚠️ 复核状态"].map(
            {True: "需要复核", False: "无需复核"}
        ).fillna("未知")

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
    <div class="hero-title">📝 ActionScribe 会议行动项助手</div>
    <div class="hero-subtitle">
        将会议录音或文字整理为清晰的行动项，并可保存到飞书多维表格或发送群通知
    </div>
</div>
""", unsafe_allow_html=True)

# Pipeline flow indicator
st.markdown("""
<div style="text-align:center; margin-bottom: 1.5rem;">
    <span class="pipeline-step">🎙️ 录音 / 文字</span>
    <span style="color:#3459c7;margin:0 0.3rem">→</span>
    <span class="pipeline-step">🔍 提取任务</span>
    <span style="color:#3459c7;margin:0 0.3rem">→</span>
    <span class="pipeline-step">⚡ 评估优先级</span>
    <span style="color:#3459c7;margin:0 0.3rem">→</span>
    <span class="pipeline-step">✅ 规范整理</span>
    <span style="color:#3459c7;margin:0 0.3rem">→</span>
    <span class="pipeline-step">📋 飞书多维表格</span>
            <span style="color:#3459c7;margin:0 0.3rem">+</span>
    <span class="pipeline-step">💬 飞书群通知</span>
</div>
""", unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ 设置")

    # Backend health check
    is_healthy = check_backend_health()
    if is_healthy:
        st.success("✅ 后端已连接")
    else:
        st.error("❌ 无法连接后端")
        st.caption(f"后端地址：`{BACKEND_URL}`")
        st.caption("请在项目根目录运行：`uvicorn api.main:app --reload --port 8000`")

    st.divider()

    st.markdown("### 🔌 外部集成")
    send_to_bitable = st.checkbox("📋 写入飞书多维表格", value=False)
    send_to_feishu_chat = st.checkbox("💬 发送飞书群通知", value=False)

    st.caption("需在本机 `.env` 配置飞书凭据。未配置或关闭时，会议分析仍会正常显示。")

    st.divider()

    st.markdown("### ℹ️ 关于 ActionScribe")
    st.markdown("""
    **会议行动项处理流程**
    
    - 🎙️ Whisper API 语音转写
    - 🤖 Groq 大模型提取任务
    - ⚡ 优先级评分（1–25）
    - 📋 写入飞书多维表格
    - 💬 发送飞书群通知
    - ☁️ 云端处理，无需本地 GPU
    """)

    st.markdown("---")
    st.caption("v1.0.0 · 基于 LangGraph 构建")

# ─────────────────────────────────────────────────────────────────────────────
# Main Layout
# ─────────────────────────────────────────────────────────────────────────────

left_col, right_col = st.columns([1, 1], gap="large")

# ── Left column: Input ──────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="section-header">📥 输入会议内容</div>', unsafe_allow_html=True)

    meeting_name = st.text_input(
        "会议名称 *" if (send_to_bitable or send_to_feishu_chat) else "会议名称",
        placeholder="例如：项目周会",
        key="meeting_name",
    )
    meeting_date = st.date_input(
        "会议日期 *" if (send_to_bitable or send_to_feishu_chat) else "会议日期",
        value=date.today(),
        key="meeting_date",
    )

    input_mode = st.radio(
        "选择输入方式：",
        ["🎙️ 上传录音", "📝 粘贴会议文字"],
        horizontal=True,
    )

    uploaded_file = None
    text_input = ""

    if input_mode == "🎙️ 上传录音":
        st.markdown("""
        <div style='background:#edf3ff;border:1px solid #d8e5fb;
        border-radius:10px;padding:0.8rem;margin-bottom:1rem;font-size:0.88rem;color:#475569;'>
        ℹ️ 文件最大 25 MB · 支持 mp3、wav、m4a、ogg、webm<br>
        音频将通过 <strong>Groq Whisper API</strong> 转写，无需本地 GPU。
        </div>
        """, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            "上传会议录音文件",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            label_visibility="collapsed",
        )

        if uploaded_file:
            st.audio(uploaded_file, format=f"audio/{uploaded_file.name.split('.')[-1]}")
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.caption(f"📁 {uploaded_file.name} · {file_size_mb:.1f} MB")

    else:
        # Sample transcript loader
        if st.button("📋 填入示例会议记录", use_container_width=True):
            st.session_state["loaded_transcript"] = SAMPLE_TRANSCRIPT

        text_input = st.text_area(
            "在此粘贴会议记录：",
            value=st.session_state.get("loaded_transcript", ""),
            height=350,
            placeholder=(
                "示例：\n"
                "张伟将在 10 月 20 日前完成支付模块接口联调。\n"
                "李娜负责在 10 月 22 日前提交测试报告。\n"
                "王强将在本周五前准备客户演示环境……"
            ),
            label_visibility="collapsed",
        )

        if text_input:
            char_count = len(text_input)
            st.caption(f"📝 共 {char_count} 个字符")

    # Process button
    st.markdown("<br>", unsafe_allow_html=True)
    has_input = bool(uploaded_file) or bool(text_input.strip())
    process_btn = st.button(
        "🚀 开始分析",
        type="primary",
        disabled=not has_input or not is_healthy,
        use_container_width=True,
    )

    if not is_healthy:
        st.caption("⚠️ 请先启动后端服务，再开始分析。")

# ── Right column: Results ────────────────────────────────────────────────────
with right_col:
    st.markdown('<div class="section-header">📊 分析结果</div>', unsafe_allow_html=True)

    if process_btn and has_input and (send_to_bitable or send_to_feishu_chat) and (
        not meeting_name.strip() or not meeting_date
    ):
        st.error("启用飞书集成时，请填写会议名称和会议日期。")
    elif process_btn and has_input:
        with st.spinner("🔄 正在处理：语音转写 → 提取任务 → 评估优先级 → 整理结果……"):
            try:
                response = None

                if input_mode == "🎙️ 上传录音" and uploaded_file:
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
                            "send_to_bitable": send_to_bitable,
                            "send_to_feishu_chat": send_to_feishu_chat,
                            "meeting_name": meeting_name.strip(),
                            "meeting_date": meeting_date.isoformat(),
                        },
                        timeout=300,  # long timeout for transcription + 3 LLM calls
                    )
                else:
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/pipeline/process",
                        data={
                            "raw_transcript": text_input,
                            "send_to_bitable": send_to_bitable,
                            "send_to_feishu_chat": send_to_feishu_chat,
                            "meeting_name": meeting_name.strip(),
                            "meeting_date": meeting_date.isoformat(),
                        },
                        timeout=120,
                    )

                if response and response.status_code == 200:
                    data = response.json()
                    actions = data.get("extracted_actions", [])
                    total = data.get("total_items", 0)
                    integration_results = data.get("integration_results", {})
                    errors = data.get("errors", [])

                    # ── Summary metrics ──────────────────────────────────────
                    st.markdown("#### 📈 任务概览")
                    m1, m2, m3, m4 = st.columns(4)

                    critical_count = sum(1 for a in actions if a.get("priority_label") == "Critical")
                    high_count = sum(1 for a in actions if a.get("priority_label") == "High")
                    review_count = sum(1 for a in actions if a.get("needs_review"))

                    with m1:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number">{total}</div>
                            <div class="metric-label">任务总数</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m2:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#b42318">{critical_count}</div>
                            <div class="metric-label">紧急</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m3:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#a15c00">{high_count}</div>
                            <div class="metric-label">高优先级</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with m4:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-number" style="color:#7650b7">{review_count}</div>
                            <div class="metric-label">需要复核</div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)

                    # ── Action Items Table ───────────────────────────────────
                    st.markdown("#### 📋 提取的行动项")
                    render_priority_table(actions)

                    if actions:
                        # Download button
                        st.download_button(
                            label="⬇️ 下载 JSON 文件",
                            data=json.dumps(actions, indent=2),
                            file_name="action_items.json",
                            mime="application/json",
                            use_container_width=True,
                        )

                    # ── Integration Status ───────────────────────────────────
                    st.markdown("#### 🔌 集成状态")
                    table_col, chat_col = st.columns(2)

                    with table_col:
                        bitable = integration_results.get("bitable", {})
                        created = bitable.get("created", 0)
                        total_records = bitable.get("total", 0)
                        if bitable.get("skipped"):
                            if send_to_bitable:
                                st.warning(f"📋 飞书多维表格尚未配置；实际写入 0/{total_records} 条。{bitable.get('error', '请检查本机配置')}")
                            else:
                                st.info("📋 飞书多维表格：本次未启用")
                        else:
                            failed = bitable.get("failed", max(0, total_records - created))
                            if bitable.get("table_created"):
                                if bitable.get("success"):
                                    st.success(f"📋 飞书多维表格：已新建数据表，并写入 {created}/{total_records} 条任务")
                                else:
                                    st.error(f"📋 飞书多维表格：数据表已新建，写入 {created}/{total_records} 条，失败 {failed} 条。{bitable.get('error', '')}")
                            elif bitable.get("success"):
                                st.success("📋 飞书多维表格：没有待写入任务。")
                            else:
                                st.error(f"📋 飞书多维表格创建或写入失败：实际写入 {created}/{total_records} 条，失败 {failed} 条。{bitable.get('error', '未知错误')}")

                    with chat_col:
                        feishu_chat = integration_results.get("feishu_chat", {})
                        if feishu_chat.get("skipped"):
                            if send_to_feishu_chat:
                                st.warning(f"💬 飞书群机器人尚未配置：{feishu_chat.get('error', '请检查本机配置')}")
                            else:
                                st.info("💬 飞书群通知：本次未启用")
                        elif feishu_chat.get("success"):
                            sent = feishu_chat.get("items_sent", 0)
                            st.success(f"💬 飞书群通知：已发送（包含 {sent} 项任务）")
                        else:
                            st.error(f"💬 飞书群通知失败：{feishu_chat.get('error', '未知错误')}")

                    # ── Transcript Preview ───────────────────────────────────
                    with st.expander("🔍 查看会议记录预览"):
                        st.text(data.get("transcript_preview", "暂无内容"))

                    # ── Errors (if any) ──────────────────────────────────────
                    if errors:
                        with st.expander(f"⚠️ 流程提示（{len(errors)} 条）"):
                            for err in errors:
                                st.warning(err)

                else:
                    status_code = response.status_code if response else "未知"
                    try:
                        detail = response.json().get("detail", "未知错误")
                    except Exception:
                        detail = "无法解析后端错误详情。"
                    for source, translated in (
                        ("Pipeline failed:", "工作流处理失败："),
                        ("Transcription failed:", "语音转写失败："),
                        ("Configuration error:", "配置错误："),
                    ):
                        if str(detail).startswith(source):
                            detail = translated + str(detail)[len(source):].strip()
                            break
                    st.error(f"❌ 分析失败（HTTP {status_code}）：{detail}")

            except requests.exceptions.ConnectionError:
                st.error(
                    "❌ 无法连接后端。请确认 FastAPI 已启动：`uvicorn api.main:app --reload --port 8000`"
                )
            except requests.exceptions.Timeout:
                st.error(
                    "⏱️ 请求超时。较大的音频文件或较长的会议记录可能需要更久。"
                )
            except Exception as e:
                st.error(f"❌ 发生未预期的错误：{str(e)}")

    else:
        # Placeholder state
        st.markdown("""
        <div style='
            text-align: center;
            padding: 4rem 2rem;
            background: #ffffff;
            border: 1px dashed #cbd8ea;
            border-radius: 16px;
            color: #64748b;
            box-shadow: 0 8px 24px rgba(31, 51, 87, 0.045);
        '>
            <div style='font-size: 3rem; margin-bottom: 1rem'>🤖</div>
            <div style='font-size: 1.1rem; font-weight: 600; color: #25324a; margin-bottom: 0.5rem'>
                准备好提取会议行动项
            </div>
            <div style='font-size: 0.9rem'>
                上传会议录音或粘贴会议记录，<br>
                然后点击 <strong>🚀 开始分析</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
