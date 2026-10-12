"""Optional Feishu Bitable and group-bot integrations.

All credentials are read from environment variables. This module never logs
access tokens or webhook URLs.
"""

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TENANT_TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
BITABLE_RECORDS_URL = f"{FEISHU_API_BASE}/bitable/v1/apps/{{app_token}}/tables/{{table_id}}/records"


def _safe_error_message(response: requests.Response, secrets: List[str]) -> str:
    """Return a concise API error without echoing configured secrets."""
    try:
        body = response.json()
        if not isinstance(body, dict):
            body = {}
        message = body.get("msg") or body.get("message") or body.get("StatusMessage")
        code = body.get("code", body.get("StatusCode"))
        if message:
            text = f"飞书返回错误 {code}: {message}" if code is not None else str(message)
        else:
            text = f"飞书 HTTP {response.status_code}"
    except (ValueError, TypeError):
        text = f"飞书 HTTP {response.status_code}"

    for secret in secrets:
        if secret:
            text = text.replace(secret, "[已隐藏]")
    return text[:500]


def _get_tenant_access_token(app_id: str, app_secret: str) -> str:
    response = requests.post(
        TENANT_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("飞书鉴权返回了无法识别的响应。") from exc
    if not isinstance(data, dict):
        raise RuntimeError("飞书鉴权返回了无法识别的响应。")

    if response.status_code >= 400 or data.get("code", 0) not in (0, "0"):
        raise RuntimeError(_safe_error_message(response, [app_id, app_secret]))

    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError("飞书鉴权成功响应中没有 tenant_access_token。")
    return token


def _field_name(env_name: str, default: str) -> str:
    return os.getenv(env_name, default).strip() or default


def _priority_label(value: Any) -> str:
    return {
        "Critical": "紧急",
        "High": "高",
        "Medium": "中",
        "Low": "低",
    }.get(str(value), str(value or "中"))


def _record_fields(task: Dict[str, Any]) -> Dict[str, Any]:
    """Map an ActionItem to configurable Feishu Bitable column names."""
    fields: Dict[str, Any] = {
        _field_name("FEISHU_FIELD_TASK", "任务"): str(task.get("task", "未命名任务")),
        _field_name("FEISHU_FIELD_OWNER", "负责人"): str(task.get("owner", "待确认")),
        _field_name("FEISHU_FIELD_DEADLINE", "截止日期"): str(task.get("deadline", "待确认")),
        _field_name("FEISHU_FIELD_PRIORITY", "优先级"): _priority_label(task.get("priority_label")),
        _field_name("FEISHU_FIELD_PRIORITY_SCORE", "优先级分数"): int(task.get("priority_score", 9)),
        _field_name("FEISHU_FIELD_URGENCY_SCORE", "紧急度分数"): int(task.get("urgency_score", 3)),
        _field_name("FEISHU_FIELD_IMPACT_SCORE", "影响度分数"): int(task.get("impact_score", 3)),
        _field_name("FEISHU_FIELD_NEEDS_REVIEW", "需要复核"): "是" if task.get("needs_review") else "否",
    }
    excerpt = task.get("source_excerpt")
    if excerpt:
        fields[_field_name("FEISHU_FIELD_SOURCE_EXCERPT", "原文摘录")] = str(excerpt)
    return fields


def dispatch_to_feishu_bitable(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create one Bitable record per task using a Feishu custom app."""
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.getenv("FEISHU_BITABLE_TABLE_ID", "").strip()
    if not all((app_id, app_secret, app_token, table_id)):
        return {
            "success": False,
            "skipped": True,
            "created": 0,
            "total": len(tasks),
            "error": "飞书多维表格尚未配置；请设置 FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_BITABLE_APP_TOKEN 和 FEISHU_BITABLE_TABLE_ID。",
        }
    if not tasks:
        return {"success": True, "created": 0, "failed": 0, "total": 0, "items": []}

    try:
        access_token = _get_tenant_access_token(app_id, app_secret)
    except requests.exceptions.RequestException:
        logger.warning("Feishu Bitable authentication request failed.")
        return {"success": False, "created": 0, "failed": len(tasks), "total": len(tasks), "error": "飞书鉴权请求失败，请检查网络连接。"}
    except RuntimeError as exc:
        return {"success": False, "created": 0, "failed": len(tasks), "total": len(tasks), "error": str(exc)}

    url = BITABLE_RECORDS_URL.format(
        app_token=quote(app_token, safe=""),
        table_id=quote(table_id, safe=""),
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    results = []
    for task in tasks:
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"fields": _record_fields(task)},
                timeout=20,
            )
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected Feishu response body")
            if response.status_code >= 400 or data.get("code", 0) not in (0, "0"):
                results.append(
                    {
                        "success": False,
                        "task": task.get("task", ""),
                        "error": _safe_error_message(response, [app_secret, access_token]),
                    }
                )
            else:
                results.append({"success": True, "task": task.get("task", "")})
        except (requests.exceptions.RequestException, ValueError):
            results.append({"success": False, "task": task.get("task", ""), "error": "创建记录请求失败，请检查网络或多维表格权限。"})

    created = sum(1 for result in results if result["success"])
    failed = len(results) - created
    logger.info("Feishu Bitable dispatch complete: %d created, %d failed.", created, failed)
    return {
        "success": failed == 0,
        "created": created,
        "failed": failed,
        "total": len(tasks),
        "items": results,
    }


def build_feishu_message(tasks: List[Dict[str, Any]]) -> str:
    """Build a concise Chinese message for a Feishu group chat."""
    ordered = sorted(tasks, key=lambda item: item.get("priority_score", 0), reverse=True)
    keyword = os.getenv("FEISHU_BOT_KEYWORD", "").strip()
    title = f"会议行动项汇总（{len(ordered)} 项）"
    if keyword:
        title = f"{keyword} {title}"
    lines = [title]
    if not ordered:
        lines.append("本次会议没有提取到待办任务。")
    for index, task in enumerate(ordered, 1):
        review = "；需要人工复核" if task.get("needs_review") else ""
        lines.append(
            f"{index}. [{_priority_label(task.get('priority_label'))} · "
            f"{task.get('priority_score', '?')}分] "
            f"{task.get('task', '未命名任务')}\n"
            f"负责人：{task.get('owner', '待确认')}；截止：{task.get('deadline', '待确认')}{review}"
        )
    return "\n\n".join(lines)


def _webhook_signature(secret: str, timestamp: str) -> str:
    sign_string = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(sign_string, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def dispatch_to_feishu_chat(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send a text summary to a Feishu custom-bot webhook."""
    webhook_url = os.getenv("FEISHU_BOT_WEBHOOK_URL", "").strip()
    secret = os.getenv("FEISHU_BOT_SECRET", "").strip()
    if not webhook_url:
        return {
            "success": False,
            "skipped": True,
            "error": "飞书群机器人尚未配置；请设置 FEISHU_BOT_WEBHOOK_URL。",
        }

    message = build_feishu_message(tasks)
    # Feishu custom bot requests have a 20 KB body limit; leave room for JSON
    # encoding overhead and preserve valid UTF-8 when truncating long summaries.
    encoded_message = message.encode("utf-8")
    if len(encoded_message) > 18_000:
        suffix = "\n\n内容过长，后续任务未完整显示；请查看页面中的结果。"
        text_limit = 18_000 - len(suffix.encode("utf-8"))
        message = encoded_message[:text_limit].decode("utf-8", errors="ignore") + suffix

    payload: Dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": message},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _webhook_signature(secret, timestamp)

    try:
        response = requests.post(webhook_url, json=payload, timeout=15)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        code = data.get("code", data.get("StatusCode", 0))
        if response.status_code >= 400 or code not in (0, "0", None):
            return {"success": False, "error": _safe_error_message(response, [webhook_url, secret])}
        logger.info("Feishu group notification sent (%d tasks).", len(tasks))
        return {"success": True, "items_sent": len(tasks)}
    except requests.exceptions.RequestException:
        logger.warning("Feishu group webhook request failed.")
        return {"success": False, "error": "飞书群通知请求失败，请检查网络或机器人 Webhook 配置。"}
