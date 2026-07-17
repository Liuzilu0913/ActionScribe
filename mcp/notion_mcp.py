"""
mcp/notion_mcp.py
──────────────────
Notion REST API integration — creates tasks in a Notion database.

Requires:
  NOTION_API_KEY      — Internal Integration Token from notion.so/my-integrations
  NOTION_DATABASE_ID  — ID of the target Notion database

The Notion database must have these properties:
  - Task Name     (title)
  - Owner         (rich_text)
  - Deadline      (date)
  - Priority      (rich_text)
  - Priority Score (number)

No GPU required — pure REST API calls via requests.
"""

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def _get_credentials() -> tuple[str, str]:
    """Retrieve Notion credentials from environment."""
    token = os.getenv("NOTION_API_KEY", "")
    db_id = os.getenv("NOTION_DATABASE_ID", "")
    return token, db_id


def create_notion_task(
    task: str,
    owner: str,
    deadline: str,
    priority_label: str,
    priority_score: int,
) -> Dict[str, Any]:
    """
    Create a single page (task) in the configured Notion database.

    Args:
        task:           Task title / description.
        owner:          Responsible person ("TBD" if unknown).
        deadline:       ISO date string "YYYY-MM-DD" or "TBD".
        priority_label: "Critical" | "High" | "Medium" | "Low"
        priority_score: Integer 1-25.

    Returns:
        {"success": True, "page_id": "...", "task": "..."}
        or
        {"success": False, "error": "...", "task": "..."}
    """
    token, db_id = _get_credentials()

    if not token or not db_id:
        logger.warning("Notion credentials missing — skipping task creation.")
        return {
            "success": False,
            "error": "Notion credentials missing. Set NOTION_API_KEY and NOTION_DATABASE_ID in .env",
            "task": task,
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    properties: Dict[str, Any] = {
        "Task Name": {
            "title": [{"text": {"content": task}}]
        },
        "Owner": {
            "rich_text": [{"text": {"content": owner}}]
        },
        "Priority": {
            "rich_text": [{"text": {"content": priority_label}}]
        },
        "Priority Score": {
            "number": priority_score
        },
    }

    # Only add Deadline if it's a valid ISO date (not "TBD")
    if deadline and deadline != "TBD":
        properties["Deadline"] = {"date": {"start": deadline}}

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }

    try:
        response = requests.post(
            NOTION_API_URL, json=payload, headers=headers, timeout=15
        )
        response.raise_for_status()
        page_data = response.json()
        logger.info("Notion: created task '%s' (page_id=%s)", task, page_data.get("id"))
        return {
            "success": True,
            "page_id": page_data.get("id"),
            "task": task,
        }
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = response.json().get("message", str(e))
        except Exception:
            error_detail = str(e)
        logger.error("Notion API error for task '%s': %s", task, error_detail)
        return {"success": False, "error": error_detail, "task": task}
    except requests.exceptions.RequestException as e:
        logger.error("Notion request failed for task '%s': %s", task, str(e))
        return {"success": False, "error": str(e), "task": task}


def dispatch_to_notion(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Send all validated action items to Notion.

    Args:
        tasks: List of validated ActionItem dicts from the formatter.

    Returns:
        Summary dict:
        {
            "total": N,
            "created": M,
            "failed": K,
            "items": [...per-task results...]
        }
    """
    if not tasks:
        return {"total": 0, "created": 0, "failed": 0, "items": []}

    results = []
    for task_data in tasks:
        result = create_notion_task(
            task=task_data.get("task", "Untitled Task"),
            owner=task_data.get("owner", "TBD"),
            deadline=task_data.get("deadline", "TBD"),
            priority_label=task_data.get("priority_label", "Medium"),
            priority_score=int(task_data.get("priority_score", 9)),
        )
        results.append(result)

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    logger.info(
        "Notion dispatch complete: %d created, %d failed out of %d total.",
        len(successful), len(failed), len(tasks),
    )

    return {
        "total": len(tasks),
        "created": len(successful),
        "failed": len(failed),
        "items": results,
    }
