from unittest.mock import patch

from integrations.feishu import dispatch_to_feishu_bitable, dispatch_to_feishu_chat


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
    monkeypatch.setenv("FEISHU_APP_ID", "app-id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app-secret")
    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base-token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "table-id")

    auth_response = type(
        "Response",
        (),
        {"status_code": 200, "json": lambda self: {"code": 0, "tenant_access_token": "temporary-token"}},
    )()
    record_response = type(
        "Response",
        (),
        {"status_code": 200, "json": lambda self: {"code": 0, "data": {"record": {"record_id": "rec-1"}}}},
    )()
    with patch("integrations.feishu.requests.post", side_effect=[auth_response, record_response]) as post:
        result = dispatch_to_feishu_bitable(
            [{"task": "准备发布说明", "owner": "小林", "deadline": "2026-10-20", "priority_score": 12}]
        )

    assert result["success"] is True
    assert result["created"] == 1
    assert post.call_count == 2
    fields = post.call_args.kwargs["json"]["fields"]
    assert fields["任务"] == "准备发布说明"
    assert fields["负责人"] == "小林"


def test_feishu_chat_webhook_uses_mocked_http(monkeypatch):
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("FEISHU_BOT_KEYWORD", "ActionScribe")
    response = type(
        "Response",
        (),
        {"status_code": 200, "json": lambda self: {"code": 0, "msg": "success"}},
    )()

    with patch("integrations.feishu.requests.post", return_value=response) as post:
        result = dispatch_to_feishu_chat([{"task": "准备发布说明", "priority_score": 12}])

    assert result["success"] is True
    payload = post.call_args.kwargs["json"]
    assert payload["msg_type"] == "text"
    assert "ActionScribe" in payload["content"]["text"]


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
        result = dispatch_to_feishu_chat([])

    assert result["success"] is True
    payload = post.call_args.kwargs["json"]
    assert payload["timestamp"] == "1800000000"
    assert payload["sign"]
