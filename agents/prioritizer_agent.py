"""
agents/prioritizer_agent.py
────────────────────────────
Assigns priority scores to extracted action items using GPT-4o.

Scoring model: urgency_score (1-5) × impact_score (1-5) = priority_score (1-25)

Priority Labels:
  20-25 → Critical
  12-19 → High
   6-11 → Medium
    1-5 → Low

Uses GPT-4o via LangChain — no GPU required.
"""

import json
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

PRIORITIZER_SYSTEM_PROMPT = """You are a project prioritization expert.

For each action item in the input array, add the following fields:
- urgency_score (int 1-5): How time-sensitive? (5 = blocks others RIGHT NOW)
- impact_score  (int 1-5): What's the business/team impact? (5 = critical revenue/customer impact)
- priority_score (int 1-25): urgency_score × impact_score
- priority_label (string): Based on priority_score:
    20-25 → "Critical"
    12-19 → "High"
     6-11 → "Medium"
      1-5 → "Low"
- reason (string): One concise sentence explaining the combined score.

Return ONLY a valid JSON array containing ALL original fields PLUS these new fields.
Do NOT drop any existing fields. No markdown, no preamble."""


# ─────────────────────────────────────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────────────────────────────────────

def run_prioritizer(raw_items: list) -> list:
    """
    Score each extracted action item with urgency × impact priority.

    Args:
        raw_items: List of raw action item dicts from run_extractor().

    Returns:
        Same list with urgency_score, impact_score, priority_score,
        priority_label, and reason added to each item.
    """
    if not raw_items:
        logger.warning("Prioritizer received empty item list — returning empty.")
        return []
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", PRIORITIZER_SYSTEM_PROMPT),
        ("user", "Action items to prioritize:\n\n{items}"),
    ])

    chain = prompt | llm

    try:
        response = chain.invoke({"items": json.dumps(raw_items, indent=2)})
        content = response.content
        content = content.replace("```json", "").replace("```", "").strip()

        scored_items = json.loads(content)
        if not isinstance(scored_items, list):
            raise ValueError("LLM returned non-list response.")

        logger.info("Prioritizer scored %d items.", len(scored_items))
        return scored_items

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Prioritizer JSON parse failed: %s. Using default scores.", str(e))
        # Fallback: assign medium scores so pipeline can continue
        for item in raw_items:
            item.setdefault("urgency_score", 3)
            item.setdefault("impact_score", 3)
            item.setdefault("priority_score", 9)
            item.setdefault("priority_label", "Medium")
            item.setdefault("reason", "Auto-scored (LLM parsing failed — review manually)")
        return raw_items

    except Exception as e:
        logger.error("Prioritizer unexpected error: %s", str(e))
        raise RuntimeError(f"Prioritizer agent failed: {str(e)}") from e
