from unittest.mock import patch

import pytest

from agents.graph import mcp_dispatcher_node, workflow


@patch("agents.graph.run_extractor")
@patch("agents.graph.run_prioritizer")
@patch("agents.graph.run_formatter")
@patch("agents.graph.dispatch_to_notion")
@patch("agents.graph.dispatch_to_slack")
def test_full_pipeline_flow(
    mock_slack, mock_notion, mock_formatter, mock_prioritizer, mock_extractor
):
    """Verify that StateGraph walks through all nodes in order and propagates state."""
    # 1. Extractor mock
    mock_extractor.return_value = [{"action": "Do work", "owner": "Vijay", "deadline": "TBD"}]

    # 2. Prioritizer mock
    mock_prioritizer.return_value = [
        {
            "action": "Do work",
            "owner": "Vijay",
            "deadline": "TBD",
            "urgency_score": 3,
            "impact_score": 4,
            "priority_score": 12,
            "priority_label": "High",
            "reason": "Impact is high.",
        }
    ]

    # 3. Formatter mock
    mock_formatter.return_value = [
        {
            "task": "Do work",
            "owner": "Vijay",
            "deadline": "TBD",
            "urgency_score": 3,
            "impact_score": 4,
            "priority_score": 12,
            "priority_label": "High",
            "confidence": 0.9,
            "needs_review": False,
            "source_excerpt": "Vijay do work.",
        }
    ]

    # 4. Dispatcher mocks
    mock_notion.return_value = {"success": True, "created": 1, "total": 1}
    mock_slack.return_value = {"success": True, "items_sent": 1}

    # Execute
    initial_state = {
        "transcript": "Vijay do work.",
        "raw_items": [],
        "priorities": [],
        "structured_items": [],
        "mcp_results": {},
        "errors": [],
    }

    result = workflow.invoke(initial_state)

    # Asserts
    assert mock_extractor.called
    assert mock_prioritizer.called
    assert mock_formatter.called
    assert mock_notion.called
    assert mock_slack.called

    assert len(result["structured_items"]) == 1
    assert result["structured_items"][0]["task"] == "Do work"
    assert result["mcp_results"]["notion"]["success"] is True
    assert result["mcp_results"]["slack"]["success"] is True
    assert len(result["errors"]) == 0


@patch("agents.graph.dispatch_to_notion")
@patch("agents.graph.dispatch_to_slack")
def test_dispatcher_respects_disabled_integrations(mock_slack, mock_notion):
    result = mcp_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_notion": False,
            "send_to_slack": False,
            "errors": [],
        }
    )

    mock_notion.assert_not_called()
    mock_slack.assert_not_called()
    assert result["mcp_results"]["notion"]["skipped"] is True
    assert result["mcp_results"]["slack"]["skipped"] is True
