"""
agents/graph.py
───────────────
LangGraph StateGraph — wires the 4-node pipeline together.

Flow: extractor → prioritizer → formatter → mcp_dispatcher → END

Uses modern LangGraph API (>=0.2). No GPU required.
"""

import logging
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents.extractor_agent import run_extractor
from agents.formatter_agent import run_formatter
from agents.prioritizer_agent import run_prioritizer
from mcp.notion_mcp import dispatch_to_notion
from mcp.slack_mcp import dispatch_to_slack

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared Pipeline State
# ─────────────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    """
    Shared state object passed between every LangGraph node.
    Each node reads from and writes back to this dict.
    """

    transcript: str                        # Input: raw transcript text
    raw_items: List[Dict[str, Any]]        # After extractor: unscored action items
    priorities: List[Dict[str, Any]]       # After prioritizer: scored action items
    structured_items: List[Dict[str, Any]] # After formatter: validated + clean items
    mcp_results: Dict[str, Any]            # After dispatcher: Notion + Slack results
    errors: List[str]                      # Accumulated error messages


# ─────────────────────────────────────────────────────────────────────────────
# Node Definitions
# ─────────────────────────────────────────────────────────────────────────────

def extractor_node(state: PipelineState) -> Dict[str, Any]:
    """Node 1 — Parse transcript and extract raw action items."""
    logger.info("[LangGraph] Running extractor_node...")
    try:
        raw_items = run_extractor(state["transcript"])
        return {"raw_items": raw_items}
    except Exception as e:
        logger.error("extractor_node failed: %s", str(e))
        return {
            "raw_items": [],
            "errors": state.get("errors", []) + [f"Extractor error: {str(e)}"],
        }


def prioritizer_node(state: PipelineState) -> Dict[str, Any]:
    """Node 2 — Assign urgency × impact scores to each item."""
    logger.info("[LangGraph] Running prioritizer_node...")
    try:
        priorities = run_prioritizer(state.get("raw_items", []))
        return {"priorities": priorities}
    except Exception as e:
        logger.error("prioritizer_node failed: %s", str(e))
        return {
            "priorities": state.get("raw_items", []),  # pass through unscored
            "errors": state.get("errors", []) + [f"Prioritizer error: {str(e)}"],
        }


def formatter_node(state: PipelineState) -> Dict[str, Any]:
    """Node 3 — Validate and normalize scored items into final schema."""
    logger.info("[LangGraph] Running formatter_node...")
    try:
        structured = run_formatter(state.get("priorities", []))
        return {"structured_items": structured}
    except Exception as e:
        logger.error("formatter_node failed: %s", str(e))
        return {
            "structured_items": [],
            "errors": state.get("errors", []) + [f"Formatter error: {str(e)}"],
        }


def mcp_dispatcher_node(state: PipelineState) -> Dict[str, Any]:
    """
    Node 4 — Dispatch validated items to Notion and Slack.

    Philosophy: If one integration fails, the other still runs.
    Both failing still returns structured_items to the caller.
    """
    logger.info("[LangGraph] Running mcp_dispatcher_node...")
    tasks = state.get("structured_items", [])
    errors = list(state.get("errors", []))

    notion_result: Dict[str, Any] = {}
    slack_result: Dict[str, Any] = {}

    try:
        notion_result = dispatch_to_notion(tasks)
        logger.info("Notion dispatch: %s", notion_result)
    except Exception as e:
        logger.error("Notion dispatch failed: %s", str(e))
        notion_result = {"success": False, "error": str(e)}
        errors.append(f"Notion dispatch error: {str(e)}")

    try:
        slack_result = dispatch_to_slack(tasks)
        logger.info("Slack dispatch: %s", slack_result)
    except Exception as e:
        logger.error("Slack dispatch failed: %s", str(e))
        slack_result = {"success": False, "error": str(e)}
        errors.append(f"Slack dispatch error: {str(e)}")

    return {
        "mcp_results": {
            "notion": notion_result,
            "slack": slack_result,
        },
        "errors": errors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Graph Assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_workflow():
    """Build and compile the LangGraph StateGraph."""
    builder = StateGraph(PipelineState)

    # Add nodes
    builder.add_node("extractor", extractor_node)
    builder.add_node("prioritizer", prioritizer_node)
    builder.add_node("formatter", formatter_node)
    builder.add_node("mcp_dispatcher", mcp_dispatcher_node)

    # Wire edges: linear pipeline
    builder.set_entry_point("extractor")
    builder.add_edge("extractor", "prioritizer")
    builder.add_edge("prioritizer", "formatter")
    builder.add_edge("formatter", "mcp_dispatcher")
    builder.add_edge("mcp_dispatcher", END)

    return builder.compile()


# Module-level compiled graph — import this in FastAPI and tests
workflow = build_workflow()
