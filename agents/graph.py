"""
agents/graph.py
───────────────
LangGraph StateGraph — wires the 4-node pipeline together.

Flow: extractor → prioritizer → formatter → integration_dispatcher → END

Uses modern LangGraph API (>=0.2). No GPU required.
"""

import logging
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents.extractor_agent import run_extractor
from agents.formatter_agent import run_formatter
from agents.prioritizer_agent import run_prioritizer
from integrations.feishu import dispatch_to_feishu_bitable, dispatch_to_feishu_chat

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
    send_to_bitable: bool                  # Whether Feishu Bitable dispatch is enabled
    send_to_feishu_chat: bool              # Whether Feishu group notification is enabled
    meeting_name: str                      # Required when writing to Bitable
    meeting_date: str                      # ISO date required when writing to Bitable
    raw_items: List[Dict[str, Any]]        # After extractor: unscored action items
    priorities: List[Dict[str, Any]]       # After prioritizer: scored action items
    structured_items: List[Dict[str, Any]] # After formatter: validated + clean items
    integration_results: Dict[str, Any]    # Feishu Bitable and group-notification results
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


def integration_dispatcher_node(state: PipelineState) -> Dict[str, Any]:
    """
    Node 4 — Dispatch validated items to Feishu Bitable and a group bot.

    Philosophy: If one integration fails, the other still runs.
    Both failing still returns structured_items to the caller.
    """
    logger.info("[LangGraph] Running integration_dispatcher_node...")
    tasks = state.get("structured_items", [])
    errors = list(state.get("errors", []))

    bitable_result: Dict[str, Any] = {}
    chat_result: Dict[str, Any] = {}

    if state.get("send_to_bitable", False):
        try:
            bitable_result = dispatch_to_feishu_bitable(
                tasks,
                meeting_name=state.get("meeting_name", ""),
                meeting_date=state.get("meeting_date", ""),
            )
            logger.info("Feishu Bitable dispatch: %s", bitable_result)
        except Exception as e:
            logger.error("Feishu Bitable dispatch failed: %s", str(e))
            bitable_result = {"success": False, "error": str(e)}
            errors.append(f"Feishu Bitable dispatch error: {str(e)}")
    else:
        bitable_result = {
            "success": False,
            "skipped": True,
            "error": "飞书多维表格写入已在本次运行中关闭。",
        }

    if state.get("send_to_feishu_chat", False):
        try:
            chat_result = dispatch_to_feishu_chat(
                tasks,
                meeting_name=state.get("meeting_name", ""),
                meeting_date=state.get("meeting_date", ""),
                bitable_result=(bitable_result if state.get("send_to_bitable", False) else None),
            )
            logger.info("Feishu group notification: %s", chat_result)
        except Exception as e:
            logger.error("Feishu group notification failed: %s", str(e))
            chat_result = {"success": False, "error": str(e)}
            errors.append(f"Feishu group notification error: {str(e)}")
    else:
        chat_result = {
            "success": False,
            "skipped": True,
            "error": "飞书群通知已在本次运行中关闭。",
        }

    return {
        "integration_results": {
            "bitable": bitable_result,
            "feishu_chat": chat_result,
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
    builder.add_node("integration_dispatcher", integration_dispatcher_node)

    # Wire edges: linear pipeline
    builder.set_entry_point("extractor")
    builder.add_edge("extractor", "prioritizer")
    builder.add_edge("prioritizer", "formatter")
    builder.add_edge("formatter", "integration_dispatcher")
    builder.add_edge("integration_dispatcher", END)

    return builder.compile()


# Module-level compiled graph — import this in FastAPI and tests
workflow = build_workflow()
