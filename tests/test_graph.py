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
        "meeting_name": "项目周会",
        "meeting_date": "2026-10-13",
        "integration_results": {},
        "errors": [],
    }

    result = workflow.invoke(initial_state)

    # Asserts
    assert mock_extractor.called
    assert mock_prioritizer.called
    assert mock_formatter.called
    assert mock_bitable.called
    assert mock_bitable.call_args.kwargs == {
        "meeting_name": "项目周会",
        "meeting_date": "2026-10-13",
    }
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


@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_chat_only_dispatch_uses_metadata_without_creating_a_table(mock_feishu_chat, mock_bitable):
    mock_feishu_chat.return_value = {"success": True}
    result = integration_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_bitable": False,
            "send_to_feishu_chat": True,
            "meeting_name": "项目周会",
            "meeting_date": "2026-10-13",
            "errors": [],
        }
    )

    mock_bitable.assert_not_called()
    mock_feishu_chat.assert_called_once()
    assert mock_feishu_chat.call_args.kwargs == {
        "meeting_name": "项目周会",
        "meeting_date": "2026-10-13",
        "bitable_result": None,
    }
    assert result["integration_results"]["feishu_chat"]["success"] is True


@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_bitable_only_dispatch_does_not_send_a_group_message(mock_feishu_chat, mock_bitable):
    mock_bitable.return_value = {"success": True, "created": 1, "total": 1}
    integration_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_bitable": True,
            "send_to_feishu_chat": False,
            "meeting_name": "项目周会",
            "meeting_date": "2026-10-13",
            "errors": [],
        }
    )

    mock_bitable.assert_called_once_with(
        [{"task": "Do work"}], meeting_name="项目周会", meeting_date="2026-10-13"
    )
    mock_feishu_chat.assert_not_called()


@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_combined_dispatch_writes_table_before_sending_shared_metadata_and_result(
    mock_feishu_chat, mock_bitable
):
    events = []
    bitable_result = {
        "success": True,
        "table_created": True,
        "table_url": "https://feishu.cn/base/base-token?table=new-table",
        "created": 1,
        "total": 1,
    }

    def write_table(tasks, **metadata):
        events.append("bitable")
        assert metadata == {"meeting_name": "项目周会", "meeting_date": "2026-10-13"}
        return bitable_result

    def send_chat(tasks, **payload):
        events.append("chat")
        return {"success": True}

    mock_bitable.side_effect = write_table
    mock_feishu_chat.side_effect = send_chat
    integration_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_bitable": True,
            "send_to_feishu_chat": True,
            "meeting_name": "项目周会",
            "meeting_date": "2026-10-13",
            "errors": [],
        }
    )

    assert events == ["bitable", "chat"]
    assert mock_feishu_chat.call_args.kwargs == {
        "meeting_name": "项目周会",
        "meeting_date": "2026-10-13",
        "bitable_result": bitable_result,
    }


@patch("agents.graph.dispatch_to_feishu_bitable")
@patch("agents.graph.dispatch_to_feishu_chat")
def test_combined_dispatch_still_sends_chat_when_bitable_write_fails(
    mock_feishu_chat, mock_bitable
):
    mock_bitable.return_value = {
        "success": False,
        "created": 0,
        "failed": 1,
        "total": 1,
        "error": "权限不足",
    }
    mock_feishu_chat.return_value = {"success": True}

    result = integration_dispatcher_node(
        {
            "structured_items": [{"task": "Do work"}],
            "send_to_bitable": True,
            "send_to_feishu_chat": True,
            "meeting_name": "项目周会",
            "meeting_date": "2026-10-13",
            "errors": [],
        }
    )

    mock_feishu_chat.assert_called_once()
    assert mock_feishu_chat.call_args.kwargs["bitable_result"]["success"] is False
    assert result["integration_results"]["feishu_chat"]["success"] is True
