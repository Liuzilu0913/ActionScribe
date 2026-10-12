from unittest.mock import patch

import pytest

from agents.graph import integration_dispatcher_node, workflow


@patch("agents.graph.run_extractor")
@patch("agents.graph.run_prioritizer")
@patch("agents.graph.run_formatter")
@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_full_pipeline_flow(
    mock_feishu_chat, mock_bitable, mock_formatter, mock_prioritizer, mock_extractor
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
    mock_bitable.return_value = {"success": True, "created": 1, "total": 1}
    mock_feishu_chat.return_value = {"success": True, "items_sent": 1}

    # Execute
    initial_state = {
        "transcript": "Vijay do work.",
        "raw_items": [],
        "priorities": [],
        "structured_items": [],
        "send_to_bitable": True,
        "send_to_feishu_chat": True,
        "integration_results": {},
        "errors": [],
    }

    result = workflow.invoke(initial_state)

    # Asserts
    assert mock_extractor.called
    assert mock_prioritizer.called
    assert mock_formatter.called
    assert mock_bitable.called
    assert mock_feishu_chat.called

    assert len(result["structured_items"]) == 1
    assert result["structured_items"][0]["task"] == "Do work"
    assert result["integration_results"]["bitable"]["success"] is True
    assert result["integration_results"]["feishu_chat"]["success"] is True
    assert len(result["errors"]) == 0


@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_dispatcher_respects_disabled_integrations(mock_feishu_chat, mock_bitable):
    result = integration_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_bitable": False,
            "send_to_feishu_chat": False,
            "errors": [],
        }
    )

    mock_bitable.assert_not_called()
    mock_feishu_chat.assert_not_called()
    assert result["integration_results"]["bitable"]["skipped"] is True
    assert result["integration_results"]["feishu_chat"]["skipped"] is True
