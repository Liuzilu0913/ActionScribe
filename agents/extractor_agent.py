"""
agents/extractor_agent.py
─────────────────────────
LLM-based meeting transcript analyzer.
Extracts all action items (explicit and implicit) as structured JSON.

Uses Groq via LangChain — no GPU required.
"""

import json
import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTOR_SYSTEM_PROMPT = """You are an expert meeting analyst and project manager.

Analyze the meeting transcript and extract ALL action items.

Rules:
- Extract both EXPLICIT actions ("John will do X by Friday") and IMPLICIT ones ("We should do X")
- If the owner is unclear, set "owner" to "TBD"
- Resolve relative deadlines against the provided meeting date. For example, if the meeting date is 2026-10-13, "tomorrow EOD" means 2026-10-14.
- Convert resolved deadlines to ISO format YYYY-MM-DD. If the meeting date is unavailable or the deadline remains ambiguous, set it to "TBD".
- Ignore pure discussion with no commitment or next step
- Mark ambiguous items with "needs_review": true

Return ONLY a valid JSON array — no markdown, no explanation, no preamble.

Output format (strict JSON array):
[
  {{
    "action": "specific, actionable task description",
    "owner": "person name or TBD",
    "deadline": "YYYY-MM-DD or TBD",
    "deadline_type": "explicit | inferred | TBD",
    "source_excerpt": "exact quote from the transcript",
    "confidence": 0.95,
    "needs_review": false
  }}
]

If there are zero action items, return an empty JSON array: []"""


# ─────────────────────────────────────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────────────────────────────────────

def run_extractor(transcript: str, meeting_date: str | None = None) -> list:
    """
    Parse a meeting transcript and extract all action items.

    Uses Groq via LangChain ChatGroq — cloud API, no GPU.

    Args:
        transcript: Raw meeting transcript text.
        meeting_date: ISO meeting date used as the reference date for relative deadlines.

    Returns:
        List of raw action item dicts. On JSON parse failure, returns a
        fallback list with a single needs_review item.
    """
    if not transcript or not transcript.strip():
        logger.warning("Empty transcript passed to extractor — returning empty list.")
        return []

    llm = ChatGroq(
        model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), temperature=0.0
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", EXTRACTOR_SYSTEM_PROMPT),
        (
            "user",
            "Meeting date for relative deadline calculations (YYYY-MM-DD): {meeting_date}\n\n"
            "Meeting Transcript:\n\n{transcript}",
        ),
    ])

    chain = prompt | llm

    try:
        response = chain.invoke({
            "transcript": transcript,
            "meeting_date": meeting_date or "not provided",
        })
        content = response.content

        # Strip markdown code fences if LLM wraps output anyway
        content = content.replace("```json", "").replace("```", "").strip()

        items = json.loads(content)
        if not isinstance(items, list):
            raise ValueError("LLM returned a non-list JSON structure.")

        logger.info("Extractor found %d action items.", len(items))
        return items

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Extractor JSON parse failed: %s", str(e))
        # Graceful fallback — pipeline continues with this marker item
        return [
            {
                "action": "Review meeting transcript manually — AI extraction failed",
                "owner": "TBD",
                "deadline": "TBD",
                "deadline_type": "TBD",
                "source_excerpt": transcript[:200],
                "confidence": 0.0,
                "needs_review": True,
            }
        ]
    except Exception as e:
        logger.error("Extractor unexpected error: %s", str(e))
        raise RuntimeError(f"Extractor agent failed: {str(e)}") from e
