<div align="center">

# 📝 ActionScribe

### *AI-Powered Meeting-to-Action Pipeline*

<p>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit"/>
  <img src="https://img.shields.io/badge/Groq-000000?style=for-the-badge&logo=groq&logoColor=white" alt="Groq"/>
  <img src="https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=chainlink&logoColor=white" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/Notion_API-000000?style=for-the-badge&logo=notion&logoColor=white" alt="Notion API"/>
  <img src="https://img.shields.io/badge/Slack_API-4A154B?style=for-the-badge&logo=slack&logoColor=white" alt="Slack API"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
</p>

<p>
  <strong>A fully automated LangGraph agent pipeline that ingests meeting audio, transcribes it, extracts actionable tasks, scores priorities, and dispatches them directly to Notion and Slack.</strong>
</p>

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)

---

## 🌟 Overview

**ActionScribe** solves the tedious process of post-meeting manual documentation. Built with a 4-node **LangGraph** agent architecture, it intelligently parses meeting transcripts (or raw audio) to find explicit and implicit action items, assigns an `urgency × impact` priority score, formats them into a strict schema, and automatically routes the tasks to your team's project management and communication tools.

Powered entirely by **Groq** for completely free, lightning-fast inference using Whisper Large v3 (Audio) and Llama-3.3-70B (LLM Extraction).

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎙️ **Audio & Text Ingestion** | Upload `.mp3`/`.wav` recordings directly, or paste raw meeting transcripts |
| ⚡ **Lightning Fast AI** | Runs on Groq's LPU infrastructure for near-instant transcription and extraction |
| 🧠 **Multi-Agent Pipeline** | LangGraph orchestrates Extractor, Prioritizer, Formatter, and Dispatcher agents |
| 📊 **Intelligent Scoring** | GPT/Llama model assigns a priority score (1-25) based on urgency and business impact |
| 🔗 **Notion Integration** | Automatically creates detailed Database pages for every extracted task |
| 📢 **Slack Broadcasting** | Posts formatted meeting summaries and task lists to designated Slack channels |
| 🌐 **Interactive Dashboard** | Beautiful Streamlit UI to monitor pipeline progress and edit tasks on the fly |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                              │
│                  (File Upload & Pipeline Run)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │  REST API POST /transcribe & /pipeline
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                             │
│                                                                  │
│  ┌───────────────┐     ┌───────────────────────────────────┐     │
│  │ Groq Whisper  │ ──> │       LangGraph Pipeline          │     │
│  │ Transcription │     │ (Extract -> Prioritize -> Format) │     │
│  └───────────────┘     └─────────────────┬─────────────────┘     │
│                                          │                       │
└──────────────────────────────────────────│──────────────────────┘
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MCP (Model Context Protocol)                   │
│          ┌───────────────────┐       ┌───────────────────┐       │
│          │ Notion API Create │       │ Slack Webhook Post│       │
│          └───────────────────┘       └───────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Python 3.11+
- **Frontend:** Streamlit
- **AI/LLM:** LangChain, LangGraph, Groq (Llama-3.3 70B & Whisper Large v3)
- **Integrations:** Notion REST API, Slack Incoming Webhooks
- **Infrastructure:** Docker, Docker Compose

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/shubham333k/ActionScribe.git
cd ActionScribe
```

### 2. Set up Virtual Environment
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```env
GROQ_API_KEY=gsk_your_key...
NOTION_API_KEY=ntn_your_key...
NOTION_DATABASE_ID=your_db_id...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### 4. Run the Application
Open two terminals:

**Terminal 1 (Backend):**
```bash
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 (Frontend):**
```bash
streamlit run ui/app.py
```
*Access the dashboard at `http://localhost:8501`*

*(Alternatively, run `docker-compose up --build`)*

---
<div align="center">
<i>Built with ❤️ by Shubham</i>
</div>
