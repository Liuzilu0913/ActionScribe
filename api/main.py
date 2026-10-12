"""
api/main.py
────────────
FastAPI application — REST endpoints for the AI Meeting-to-Action Pipeline.

Endpoints:
  GET  /api/health                  — Health check
  POST /api/v1/transcribe           — Audio → transcript only
  POST /api/v1/pipeline/process     — Full pipeline (audio or transcript → tasks → dispatch)

No GPU required — all processing via cloud APIs.
"""

import io
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # Load .env before importing anything that reads env vars

from agents.graph import workflow
from transcriber.whisper_api import WhisperTranscriber

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Meeting-to-Action API",
    version="1.0.0",
    description=(
        "Upload a meeting audio file or paste a transcript. "
        "The pipeline extracts action items, assigns priorities, "
        "and dispatches tasks to Notion and Slack automatically."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB — Groq free-tier audio limit

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/m4a",
    "audio/mp4",
    "audio/ogg",
    "audio/webm",
    "video/mp4",  # Some browsers report mp4 audio as video/mp4
}


def get_transcriber() -> WhisperTranscriber:
    """Lazily create the transcriber (validates API key on first call)."""
    return WhisperTranscriber()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health_check():
    """Service health check — returns status and version."""
    return {
        "status": "healthy",
        "service": "meeting-action-pipeline",
        "version": "1.0.0",
    }


@app.post("/api/v1/transcribe", tags=["Transcription"])
async def transcribe_audio(audio_file: UploadFile = File(...)):
    """
    Transcribe an audio file to text using Groq Whisper API (cloud).

    - Supported formats: mp3, wav, m4a, ogg, webm, mp4
    - Max file size: 25 MB
    - Returns: { "transcript": "...", "filename": "..." }
    """
    contents = await audio_file.read()

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 25 MB (Whisper API limit).",
        )

    if audio_file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported audio format: {audio_file.content_type}. "
                f"Allowed: mp3, wav, m4a, ogg, webm, mp4"
            ),
        )

    try:
        transcriber = get_transcriber()
        transcript = transcriber.transcribe(
            io.BytesIO(contents),
            filename=audio_file.filename or "meeting.mp3",
        )
        return {"transcript": transcript, "filename": audio_file.filename}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {str(e)}")


@app.post("/api/v1/pipeline/process", tags=["Pipeline"])
async def process_meeting(
    audio_file: Optional[UploadFile] = File(None),
    raw_transcript: Optional[str] = Form(None),
    send_to_notion: bool = Form(True),
    send_to_slack: bool = Form(True),
):
    """
    Full pipeline: Audio or Transcript → Action Items → Notion + Slack.

    Provide ONE of:
    - `audio_file`     — multipart upload (mp3, wav, m4a, ogg, webm)
    - `raw_transcript` — plain text form field

    Returns:
    ```json
    {
        "status": "success",
        "transcript_preview": "...",
        "total_items": 4,
        "extracted_actions": [...],
        "mcp_results": {
            "notion": { "total": 4, "created": 4, ... },
            "slack":  { "success": true, ... }
        },
        "errors": []
    }
    ```
    """
    if not audio_file and not raw_transcript:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'audio_file' (multipart) or 'raw_transcript' (form field).",
        )

    # ── Step 1: Resolve transcript ────────────────────────────────────────────
    resolved_transcript = ""

    if audio_file:
        contents = await audio_file.read()
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Audio file too large. Maximum size is 25 MB.",
            )
        try:
            transcriber = get_transcriber()
            resolved_transcript = transcriber.transcribe(
                io.BytesIO(contents),
                filename=audio_file.filename or "meeting.mp3",
            )
            logger.info("Transcription complete — %d chars", len(resolved_transcript))
        except (RuntimeError, ValueError) as e:
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    else:
        resolved_transcript = (raw_transcript or "").strip()

    if not resolved_transcript:
        raise HTTPException(
            status_code=400,
            detail="Transcript is empty. Please provide audio or non-empty text.",
        )

    # ── Step 2: LangGraph pipeline ────────────────────────────────────────────
    initial_state = {
        "transcript": resolved_transcript,
        "send_to_notion": send_to_notion,
        "send_to_slack": send_to_slack,
        "raw_items": [],
        "priorities": [],
        "structured_items": [],
        "mcp_results": {},
        "errors": [],
    }

    try:
        logger.info("Starting LangGraph pipeline...")
        final_state = workflow.invoke(initial_state)
        logger.info(
            "Pipeline complete — %d items extracted.",
            len(final_state.get("structured_items", [])),
        )

        preview = resolved_transcript[:500]
        if len(resolved_transcript) > 500:
            preview += "..."

        return {
            "status": "success",
            "transcript_preview": preview,
            "total_items": len(final_state.get("structured_items", [])),
            "extracted_actions": final_state.get("structured_items", []),
            "mcp_results": final_state.get("mcp_results", {}),
            "errors": final_state.get("errors", []),
        }

    except Exception as e:
        logger.exception("LangGraph pipeline crashed.")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {str(e)}",
        )
