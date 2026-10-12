from unittest.mock import patch

from mcp.notion_mcp import create_notion_task
from mcp.slack_mcp import dispatch_to_slack


def test_integrations_skip_without_credentials(monkeypatch):
    """Optional integrations report missing credentials without making HTTP calls."""
    monkeypatch.setenv("NOTION_API_KEY", "")
    monkeypatch.setenv("NOTION_DATABASE_ID", "")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")

    with patch("mcp.notion_mcp.requests.post") as notion_post, patch(
        "mcp.slack_mcp.requests.post"
    ) as slack_post:
        notion = create_notion_task("Prepare release notes", "Alex", "TBD", "Medium", 9)
        slack = dispatch_to_slack([{"task": "Prepare release notes"}])

    assert notion["success"] is False
    assert "missing" in notion["error"].lower()
    assert slack["success"] is False
    assert "missing" in slack["error"].lower()
    notion_post.assert_not_called()
    slack_post.assert_not_called()
