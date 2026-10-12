"""
transcriber/whisper_api.py
──────────────────────────
Groq Whisper API wrapper for cloud-based audio transcription.
No GPU required — all processing happens on Groq's servers.

Groq API usage limits and pricing depend on the account plan.
Supported audio formats: mp3, mp4, mpeg, mpga, m4a, wav, webm
Max file size: 25 MB
"""

import os
from typing import BinaryIO, Optional

from groq import Groq


class WhisperTranscriber:
    """
    Groq Whisper API wrapper.
    Cloud transcription — no GPU required.
    Get an API key at: https://console.groq.com/keys
    """

    SUPPORTED_FORMATS = ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
    MAX_FILE_SIZE_MB = 25

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the transcriber with a Groq API key.

        Args:
            api_key: Groq API key. Falls back to GROQ_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is missing. "
                "Get a key at https://console.groq.com/keys and set it in your .env file."
            )
        self.client = Groq(api_key=self.api_key)

    def transcribe(
        self,
        audio_file: BinaryIO,
        filename: str = "meeting.mp3",
        language: Optional[str] = "en",
    ) -> str:
        """
        Convert an audio file to text using Groq Whisper API.

        Args:
            audio_file: Binary file-like object (e.g., io.BytesIO)
            filename:   Original filename — extension determines format
            language:   ISO-639-1 language code ("en", "hi", etc.)
                        Pass None for automatic language detection.

        Returns:
            Transcribed text as a plain string.

        Raises:
            RuntimeError: If the Whisper API call fails.
        """
        try:
            ext = filename.rsplit(".", 1)[-1].lower()
            mime_map = {
                "mp3": "audio/mpeg",
                "mp4": "audio/mp4",
                "mpeg": "audio/mpeg",
                "mpga": "audio/mpeg",
                "m4a": "audio/mp4",
                "wav": "audio/wav",
                "webm": "audio/webm",
                "ogg": "audio/ogg",
            }
            mime_type = mime_map.get(ext, "audio/mpeg")

            transcription = self.client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=(filename, audio_file, mime_type),
                language=language,
                response_format="text",
            )
            return str(transcription)

        except Exception as e:
            raise RuntimeError(f"Groq Whisper transcription failed: {str(e)}") from e

    def transcribe_with_timestamps(
        self,
        audio_file: BinaryIO,
        filename: str = "meeting.mp3",
        language: Optional[str] = "en",
    ) -> dict:
        """
        Transcribe audio and return text with per-segment timestamps.
        """
        try:
            ext = filename.rsplit(".", 1)[-1].lower()
            mime_map = {
                "mp3": "audio/mpeg", "mp4": "audio/mp4", "m4a": "audio/mp4",
                "wav": "audio/wav",  "webm": "audio/webm", "ogg": "audio/ogg",
            }
            mime_type = mime_map.get(ext, "audio/mpeg")

            result = self.client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=(filename, audio_file, mime_type),
                language=language,
                response_format="verbose_json",
            )
            return {
                "text": result.text,
                "segments": [
                    {
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", ""),
                    }
                    for seg in (result.segments or [])
                ],
            }

        except Exception as e:
            raise RuntimeError(f"Groq Whisper (verbose) failed: {str(e)}") from e
