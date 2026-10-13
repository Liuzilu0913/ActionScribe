from unittest.mock import patch

import pytest
import requests

from integrations.feishu import (
    _next_table_name,
    build_meeting_table_base_name,
    build_feishu_message,
    dispatch_to_feishu_bitable,
    dispatch_to_feishu_chat,
)


class MockResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


def configure_bitable(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base-token")
    monkeypatch.setenv("FEISHU_FIELD_TASK", "任务描述")
    monkeypatch.setenv("FEISHU_FIELD_OWNER", "负责人")
    monkeypatch.setenv("FEISHU_FIELD_DEADLINE", "截止日期")
    monkeypatch.setenv("FEISHU_FIELD_PRIORITY", "优先级")
    monkeypatch.setenv("FEISHU_FIELD_PRIORITY_SCORE", "优先级分数")
    monkeypatch.setenv("FEISHU_FIELD_URGENCY_SCORE", "紧急度分数")
    monkeypatch.setenv("FEISHU_FIELD_IMPACT_SCORE", "影响度分数")
    monkeypatch.setenv("FEISHU_FIELD_NEEDS_REVIEW", "复核状态")
    monkeypatch.setenv("FEISHU_FIELD_SOURCE_EXCERPT", "原文摘录")


def mock_successful_post(url, **kwargs):
    if url.endswith("/tenant_access_token/internal"):
        return MockResponse({"code": 0, "tenant_access_token": "temporary-token"})
    if url.endswith("/tables"):
        return MockResponse({"code": 0, "data": {"table_id": "table-new"}})
    return MockResponse({"code": 0, "data": {"record": {"record_id": "rec-1"}}})


def test_feishu_integrations_skip_without_credentials(monkeypatch):
    """Optional Feishu integrations do not make HTTP calls until configured."""
    for name in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_BITABLE_APP_TOKEN",
        "FEISHU_BITABLE_TABLE_ID",
        "FEISHU_BOT_WEBHOOK_URL",
    ):
        monkeypatch.setenv(name, "")

    with patch("integrations.feishu.requests.post") as post:
        bitable = dispatch_to_feishu_bitable([{"task": "准备发布说明"}])
        chat = dispatch_to_feishu_chat([{"task": "准备发布说明"}])

    assert bitable["success"] is False and bitable["skipped"] is True
    assert chat["success"] is False and chat["skipped"] is True
    post.assert_not_called()


def test_bitable_dispatch_creates_records_with_mocked_http(monkeypatch):
    configure_bitable(monkeypatch)
    with patch(
        "integrations.feishu.requests.get",
        return_value=MockResponse({"code": 0, "data": {"items": [], "has_more": False}}),
    ) as get, patch("integrations.feishu.requests.post", side_effect=mock_successful_post) as post:
        result = dispatch_to_feishu_bitable(
            [{"task": "准备发布说明", "owner": "小林", "deadline": "2026-10-20", "priority_score": 12}],
            meeting_name="项目周会",
            meeting_date="2026-10-13",
        )

    assert result["success"] is True
    assert result["created"] == 1
    assert result["failed"] == 0
    assert result["table_created"] is True
    assert result["table_name"] == "2026-10-13_项目周会"
    assert result["table_id"] == "table-new"
    assert result["table_url"].endswith("?table=table-new")
    assert get.call_count == 1
    assert post.call_count == 3
    table_payload = post.call_args_list[1].kwargs["json"]["table"]
    assert table_payload["name"] == "2026-10-13_项目周会"
    assert table_payload["default_view_name"] == "表格"
    assert table_payload["fields"] == [
        {"field_name": "任务描述", "type": 1},
        {"field_name": "负责人", "type": 1},
        {"field_name": "截止日期", "type": 1},
        {"field_name": "优先级", "type": 1},
        {"field_name": "优先级分数", "type": 2},
        {"field_name": "紧急度分数", "type": 2},
        {"field_name": "影响度分数", "type": 2},
        {"field_name": "复核状态", "type": 1},
        {"field_name": "原文摘录", "type": 1},
    ]
    record_call = post.call_args_list[2]
    assert "/tables/table-new/records" in record_call.args[0]
    assert record_call.kwargs["json"]["fields"]["任务描述"] == "准备发布说明"
    assert record_call.kwargs["json"]["fields"]["负责人"] == "小林"


def test_bitable_table_names_use_maximum_existing_suffix():
    base_name = "2026-10-13_项目周会"

    assert build_meeting_table_base_name(" 项目周会 ", "2026-10-13") == base_name
    assert _next_table_name(base_name, []) == base_name
    assert _next_table_name(base_name, [base_name]) == f"{base_name}_1"
    assert _next_table_name(base_name, [base_name, f"{base_name}_1"]) == f"{base_name}_2"
    assert _next_table_name(base_name, [f"{base_name}_1", f"{base_name}_3"]) == f"{base_name}_4"
    long_base = build_meeting_table_base_name("项目周会" * 100, "2026-10-13")
    assert len(long_base) <= 96
    assert len(_next_table_name(long_base, [long_base])) <= 100
    with pytest.raises(ValueError, match="不支持的字符"):
        build_meeting_table_base_name("项目/周会", "2026-10-13")


def test_bitable_dispatch_increments_names_across_repeated_meetings(monkeypatch):
    configure_bitable(monkeypatch)
    existing_tables = []
    created_names = []
    table_counter = 0

    def get_tables(url, **kwargs):
        return MockResponse(
            {
                "code": 0,
                "data": {"items": list(existing_tables), "has_more": False},
            }
        )

    def post_feishu(url, **kwargs):
        nonlocal table_counter
        if url.endswith("/tenant_access_token/internal"):
            return MockResponse({"code": 0, "tenant_access_token": "temporary-token"})
        if url.endswith("/tables"):
            table_counter += 1
            table_name = kwargs["json"]["table"]["name"]
            created_names.append(table_name)
            existing_tables.append({"name": table_name, "table_id": f"table-{table_counter}"})
            return MockResponse({"code": 0, "data": {"table_id": f"table-{table_counter}"}})
        return MockResponse({"code": 0, "data": {"record": {"record_id": "rec-1"}}})

    with patch("integrations.feishu.requests.get", side_effect=get_tables), patch(
        "integrations.feishu.requests.post", side_effect=post_feishu
    ):
        results = [
            dispatch_to_feishu_bitable(
                [{"task": "提交周报"}], "项目周会", "2026-10-13"
            )
            for _ in range(3)
        ]

    assert created_names == [
        "2026-10-13_项目周会",
        "2026-10-13_项目周会_1",
        "2026-10-13_项目周会_2",
    ]
    assert all(result["success"] for result in results)


def test_bitable_creates_a_table_even_when_no_tasks_were_extracted(monkeypatch):
    configure_bitable(monkeypatch)
    with patch(
        "integrations.feishu.requests.get",
        return_value=MockResponse({"code": 0, "data": {"items": [], "has_more": False}}),
    ), patch("integrations.feishu.requests.post", side_effect=mock_successful_post) as post:
        result = dispatch_to_feishu_bitable([], "项目周会", "2026-10-13")

    assert result["success"] is True
    assert result["table_created"] is True
    assert result["created"] == 0
    assert result["failed"] == 0
    assert post.call_count == 2  # Authentication and table creation; no record requests.


def test_bitable_table_creation_failure_reports_zero_written(monkeypatch):
    configure_bitable(monkeypatch)

    def post_feishu(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            return MockResponse({"code": 0, "tenant_access_token": "temporary-token"})
        return MockResponse(
            {"code": 1254015, "msg": "FieldTypeValueNotMatch"}, status_code=400
        )

    with patch(
        "integrations.feishu.requests.get",
        return_value=MockResponse({"code": 0, "data": {"items": [], "has_more": False}}),
    ), patch("integrations.feishu.requests.post", side_effect=post_feishu) as post:
        result = dispatch_to_feishu_bitable(
            [{"task": "准备发布说明"}], "项目周会", "2026-10-13"
        )

    assert result["success"] is False
    assert result["table_created"] is False
    assert result["created"] == 0
    assert result["failed"] == result["total"] == 1
    assert result["table_name"] == "2026-10-13_项目周会"
    assert "1254015" in result["error"]
    assert post.call_count == 2


def test_bitable_uncertain_table_create_network_failure_is_reported(monkeypatch):
    configure_bitable(monkeypatch)

    def post_feishu(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            return MockResponse({"code": 0, "tenant_access_token": "temporary-token"})
        raise requests.exceptions.Timeout()

    with patch(
        "integrations.feishu.requests.get",
        return_value=MockResponse({"code": 0, "data": {"items": [], "has_more": False}}),
    ), patch("integrations.feishu.requests.post", side_effect=post_feishu):
        result = dispatch_to_feishu_bitable(
            [{"task": "准备发布说明"}], "项目周会", "2026-10-13"
        )

    assert result["success"] is False
    assert result["table_created"] is None
    assert result["table_creation_uncertain"] is True
    assert result["created"] == 0
    assert result["failed"] == result["total"] == 1
    assert "无法确认" in result["error"]


def test_bitable_record_failure_reports_created_table_and_actual_count(monkeypatch):
    configure_bitable(monkeypatch)

    def post_feishu(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            return MockResponse({"code": 0, "tenant_access_token": "temporary-token"})
        if url.endswith("/tables"):
            return MockResponse({"code": 0, "data": {"table_id": "table-new"}})
        return MockResponse({"code": 1254045, "msg": "FieldNameNotFound"}, status_code=400)

    with patch(
        "integrations.feishu.requests.get",
        return_value=MockResponse({"code": 0, "data": {"items": [], "has_more": False}}),
    ), patch("integrations.feishu.requests.post", side_effect=post_feishu):
        result = dispatch_to_feishu_bitable(
            [{"task": "准备发布说明"}], "项目周会", "2026-10-13"
        )

    assert result["success"] is False
    assert result["table_created"] is True
    assert result["table_id"] == "table-new"
    assert result["table_url"].endswith("?table=table-new")
    assert result["created"] == 0
    assert result["failed"] == result["total"] == 1
    assert "1254045" in result["items"][0]["error"]


def test_feishu_chat_webhook_uses_mocked_http(monkeypatch):
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("FEISHU_BOT_KEYWORD", "ActionScribe")
    response = type(
        "Response",
        (),
        {"status_code": 200, "json": lambda self: {"code": 0, "msg": "success"}},
    )()

    with patch("integrations.feishu.requests.post", return_value=response) as post:
        result = dispatch_to_feishu_chat(
            [{"task": "准备发布说明", "priority_score": 12}],
            meeting_name="项目周会",
            meeting_date="2026-10-13",
        )

    assert result["success"] is True
    payload = post.call_args.kwargs["json"]
    assert payload["msg_type"] == "text"
    assert "ActionScribe" in payload["content"]["text"]
    assert "会议名称：项目周会" in payload["content"]["text"]
    assert "会议日期：2026-10-13" in payload["content"]["text"]


def test_feishu_chat_adds_signature_when_configured(monkeypatch):
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("FEISHU_BOT_SECRET", "signature-secret")
    response = type(
        "Response",
        (),
        {"status_code": 200, "json": lambda self: {"code": 0, "msg": "success"}},
    )()

    with patch("integrations.feishu.time.time", return_value=1_800_000_000), patch(
        "integrations.feishu.requests.post", return_value=response
    ) as post:
        result = dispatch_to_feishu_chat(
            [], meeting_name="项目周会", meeting_date="2026-10-13"
        )

    assert result["success"] is True
    payload = post.call_args.kwargs["json"]
    assert payload["timestamp"] == "1800000000"
    assert payload["sign"]


def test_feishu_chat_includes_link_from_the_current_successful_bitable_run(monkeypatch):
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK_URL", "https://example.invalid/webhook")
    response = MockResponse({"code": 0, "msg": "success"})
    tasks = [
        {
            "task": "Complete the payment module API integration",
            "owner": "Shubham",
            "deadline": "2026-07-25",
            "priority_label": "Critical",
            "priority_score": 25,
        }
    ]

    with patch("integrations.feishu.requests.post", return_value=response) as post:
        result = dispatch_to_feishu_chat(
            tasks,
            meeting_name="项目周会",
            meeting_date="2026-10-13",
            bitable_result={
                "success": True,
                "table_created": True,
                "table_url": "https://feishu.cn/base/base-token?table=table-new",
                "created": 1,
                "total": 1,
            },
        )

    message = post.call_args.kwargs["json"]["content"]["text"]
    assert result["success"] is True
    assert "会议行动项汇总（1 项）\n会议名称：项目周会\n会议日期：2026-10-13" in message
    assert "任务表：https://feishu.cn/base/base-token?table=table-new" in message
    assert "[紧急 · 25分] Complete the payment module API integration" in message
    assert "负责人：Shubham；截止：2026-07-25" in message


def test_feishu_chat_reports_bitable_failure_without_adding_a_table_link():
    message = build_feishu_message(
        [{"task": "准备发布说明", "priority_score": 12}],
        "项目周会",
        "2026-10-13",
        {
            "success": False,
            "created": 1,
            "failed": 1,
            "total": 2,
            "table_url": "https://feishu.cn/base/base-token?table=old-table",
            "error": "一条记录字段不匹配。",
        },
    )

    assert "多维表格写入失败：实际写入 1/2 条；一条记录字段不匹配。" in message
    assert "任务表：" not in message
    assert "old-table" not in message


def test_feishu_chat_only_message_has_meeting_details_and_no_table_link():
    message = build_feishu_message([], "项目周会", "2026-10-13")

    assert "会议名称：项目周会" in message
    assert "会议日期：2026-10-13" in message
    assert "任务表：" not in message
    assert "多维表格写入" not in message
