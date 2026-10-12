"""
agents/formatter_agent.py
──────────────────────────
Validates and normalizes scored action items using Pydantic structured output.

Guarantees every action item conforms to the ActionItem schema before
being dispatched to Notion/Slack.

Uses Groq with structured output — no GPU required.
"""

import logging
import os
from typing import List, Optional

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas (these are the data contracts)
# ─────────────────────────────────────────────────────────────────────────────

class ActionItem(BaseModel):
    """Final validated action item — matches Notion + Slack payload schema."""

    task: str = Field(description="Clear, actionable task description")
    owner: str = Field(description="Person responsible for the task, or 'TBD'")
    deadline: str = Field(description="ISO date YYYY-MM-DD or 'TBD'")
    urgency_score: int = Field(ge=1, le=5, description="Urgency rating 1-5")
    impact_score: int = Field(ge=1, le=5, description="Impact rating 1-5")
    priority_score: int = Field(ge=1, le=25, description="urgency_score × impact_score")
    priority_label: str = Field(description="Critical / High / Medium / Low")
    confidence: float = Field(ge=0.0, le=1.0, description="AI extraction confidence 0.0-1.0")
    needs_review: bool = Field(default=False, description="True if manual review is recommended")
    source_excerpt: Optional[str] = Field(
        default=None, description="Original quote from transcript"
    )


class MeetingOutput(BaseModel):
    """Container holding all validated action items for a meeting."""

    actions: List[ActionItem]


# ─────────────────────────────────────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────────────────────────────────────

def run_formatter(prioritized_items: list) -> list:
    """
    Normalize and validate prioritized items against the ActionItem schema.

    Uses Groq with structured output (function calling under the hood)
    to guarantee schema compliance.

    Args:
        prioritized_items: List of dicts from run_prioritizer().

    Returns:
        List of dicts, each validated against ActionItem schema.
        Falls back to best-effort normalization if structured output fails.
    """
    if not prioritized_items:
        logger.warning("Formatter received empty list — returning empty.")
        return []

    llm = ChatGroq(
        model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), temperature=0.0
    )
    structured_llm = llm.with_structured_output(MeetingOutput)

    instruction = (
        "Normalize and validate these action items into the required schema. "
        "Map the 'action' field to 'task'. "
        "Set urgency_score=3 and impact_score=3 if they are missing. "
        "Recalculate priority_score = urgency_score × impact_score if it seems wrong. "
        f"Items:\n\n{prioritized_items}"
    )

    try:
        result: MeetingOutput = structured_llm.invoke(instruction)
        formatted = [item.model_dump() for item in result.actions]
        logger.info("Formatter validated %d items.", len(formatted))
        return formatted

    except Exception as e:
        logger.error("Formatter structured output failed: %s. Falling back.", str(e))
        # Fallback: manually normalize without LLM call
        return _manual_normalize(prioritized_items)


def _manual_normalize(items: list) -> list:
    """
    Best-effort normalization without LLM — used as a fallback.
    Maps 'action' → 'task' and fills in defaults for missing fields.
    """
    normalized = []
    for raw in items:
        try:
            urgency = int(raw.get("urgency_score", 3))
            impact = int(raw.get("impact_score", 3))
            priority = urgency * impact

            if priority >= 20:
                label = "Critical"
            elif priority >= 12:
                label = "High"
            elif priority >= 6:
                label = "Medium"
            else:
                label = "Low"

            item = ActionItem(
                task=raw.get("task") or raw.get("action", "Unknown task"),
                owner=raw.get("owner", "TBD"),
                deadline=raw.get("deadline", "TBD"),
                urgency_score=max(1, min(5, urgency)),
                impact_score=max(1, min(5, impact)),
                priority_score=max(1, min(25, priority)),
                priority_label=raw.get("priority_label", label),
                confidence=float(raw.get("confidence", 0.5)),
                needs_review=bool(raw.get("needs_review", False)),
                source_excerpt=raw.get("source_excerpt"),
            )
            normalized.append(item.model_dump())
        except Exception as exc:
            logger.warning("Skipping malformed item during fallback normalization: %s", exc)
    return normalized
