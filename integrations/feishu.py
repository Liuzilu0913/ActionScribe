"""Optional Feishu Bitable and group-bot integrations.

All credentials are read from environment variables. This module never logs
access tokens or webhook URLs.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from datetime import date
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, quote, urlparse

import requests

logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
TENANT_TOKEN_URL = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
BITABLE_TABLES_URL = f"{FEISHU_API_BASE}/bitable/v1/apps/{{app_token}}/tables"
BITABLE_RECORDS_URL = f"{FEISHU_API_BASE}/bitable/v1/apps/{{app_token}}/tables/{{table_id}}/records"
MAX_BITABLE_TABLE_NAME_LENGTH = 100
_BITABLE_TABLE_CREATE_LOCK = threading.Lock()


class FeishuAPIError(RuntimeError):
    """An API response with an HTTP or Feishu application error."""

    def __init__(self, message: str, code: Any = None, table_creation_uncertain: bool = False):
        super().__init__(message)
        self.code = str(code) if code is not None else None
        self.table_creation_uncertain = table_creation_uncertain


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


def _bitable_field_specs() -> List[Dict[str, Any]]:
    """Return the new table schema using the local column-name mappings."""
    return [
        {"field_name": _field_name("FEISHU_FIELD_TASK", "任务"), "type": 1},
        {"field_name": _field_name("FEISHU_FIELD_OWNER", "负责人"), "type": 1},
        {"field_name": _field_name("FEISHU_FIELD_DEADLINE", "截止日期"), "type": 1},
        {"field_name": _field_name("FEISHU_FIELD_PRIORITY", "优先级"), "type": 1},
        {"field_name": _field_name("FEISHU_FIELD_PRIORITY_SCORE", "优先级分数"), "type": 2},
        {"field_name": _field_name("FEISHU_FIELD_URGENCY_SCORE", "紧急度分数"), "type": 2},
        {"field_name": _field_name("FEISHU_FIELD_IMPACT_SCORE", "影响度分数"), "type": 2},
        {"field_name": _field_name("FEISHU_FIELD_NEEDS_REVIEW", "需要复核"), "type": 1},
        {"field_name": _field_name("FEISHU_FIELD_SOURCE_EXCERPT", "原文摘录"), "type": 1},
    ]


def normalize_meeting_metadata(meeting_name: str, meeting_date: str) -> Tuple[str, str]:
    """Validate required metadata and return a trimmed name and ISO date."""
    title = str(meeting_name or "").strip()
    if not title:
        raise ValueError("会议名称不能为空。")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meeting_date or "")):
        raise ValueError("会议日期必须使用 YYYY-MM-DD 格式。")
    try:
        normalized_date = date.fromisoformat(meeting_date).isoformat()
    except ValueError as exc:
        raise ValueError("会议日期不是有效日期。") from exc

    if any(ord(character) < 32 for character in title):
        raise ValueError("会议名称不能包含换行或控制字符。")
    return title, normalized_date


def build_meeting_table_base_name(meeting_name: str, meeting_date: str) -> str:
    """Validate and format the meeting name within Feishu's table-name limit."""
    title, normalized_date = normalize_meeting_metadata(meeting_name, meeting_date)

    forbidden = "/\\?*[]:"
    if any(character in title for character in forbidden):
        raise ValueError("会议名称包含飞书数据表不支持的字符：/ \\ ? * [ ] :。请修改会议名称后重试。")

    prefix = f"{normalized_date}_"
    # Reserve room for a numeric collision suffix while keeping the full name
    # below Feishu's 100-character table-name limit.
    max_base_length = MAX_BITABLE_TABLE_NAME_LENGTH - len("_999")
    max_title_length = max_base_length - len(prefix)
    if len(prefix) + len(title) > max_base_length:
        title = title[: max(0, max_title_length - 1)] + "…"
    return prefix + title


def _next_table_name(base_name: str, existing_names: List[str]) -> str:
    """Choose the base name or the next suffix after the highest existing one."""
    suffix_pattern = re.compile(rf"^{re.escape(base_name)}_(\d+)$")
    suffixes = [
        int(match.group(1))
        for name in existing_names
        if (match := suffix_pattern.fullmatch(name))
    ]
    base_exists = base_name in existing_names
    if not base_exists and not suffixes:
        return base_name

    suffix = max([0, *suffixes]) + 1
    candidate = f"{base_name}_{suffix}"
    if len(candidate) > MAX_BITABLE_TABLE_NAME_LENGTH:
        raise ValueError("会议名称过长，无法在飞书数据表名称限制内添加重名后缀。")
    return candidate


def _feishu_response_data(response: requests.Response, secrets: List[str]) -> Dict[str, Any]:
    """Parse a Feishu response and raise a sanitized error for failed calls."""
    try:
        data = response.json()
    except ValueError as exc:
        raise FeishuAPIError("飞书返回了无法识别的响应。") from exc
    if not isinstance(data, dict):
        raise FeishuAPIError("飞书返回了无法识别的响应。")

    code = data.get("code", 0)
    if response.status_code >= 400 or code not in (0, "0"):
        raise FeishuAPIError(_safe_error_message(response, secrets), code)
    return data


def _list_bitable_table_names(app_token: str, access_token: str, secrets: List[str]) -> List[str]:
    """Read every existing table name in the configured Base."""
    url = BITABLE_TABLES_URL.format(app_token=quote(app_token, safe=""))
    headers = {"Authorization": f"Bearer {access_token}"}
    names: List[str] = []
    page_token = None
    seen_tokens = set()

    while True:
        params: Dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        response = requests.get(url, headers=headers, params=params, timeout=20)
        data = _feishu_response_data(response, secrets)
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            raise FeishuAPIError("飞书列出数据表时返回了无法识别的响应。")
        items = payload.get("items", payload.get("tables", [])) or []
        if not isinstance(items, list):
            raise FeishuAPIError("飞书列出数据表时返回了无法识别的数据表列表。")
        names.extend(
            str(item["name"])
            for item in items
            if isinstance(item, dict) and item.get("name") is not None
        )

        if not payload.get("has_more"):
            break
        next_token = payload.get("page_token")
        if not next_token or next_token in seen_tokens:
            raise FeishuAPIError("飞书数据表列表分页信息不完整，已停止创建以避免名称冲突。")
        seen_tokens.add(next_token)
        page_token = next_token

    return names


def _create_bitable_table(
    app_token: str,
    access_token: str,
    table_name: str,
    field_specs: List[Dict[str, Any]],
    secrets: List[str],
) -> str:
    """Create a table and its fields in one request; return the new table ID."""
    url = BITABLE_TABLES_URL.format(app_token=quote(app_token, safe=""))
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "table": {
                "name": table_name,
                "default_view_name": "表格",
                "fields": field_specs,
            }
        },
        timeout=20,
    )
    data = _feishu_response_data(response, secrets)
    payload = data.get("data") or {}
    if not isinstance(payload, dict):
        raise FeishuAPIError("飞书已响应建表请求，但没有返回可识别的数据表信息。")
    table = payload.get("table") or {}
    table_id = payload.get("table_id") or (table.get("table_id") if isinstance(table, dict) else None)
    if not table_id:
        raise FeishuAPIError(
            "飞书已响应建表请求，但没有返回 table_id；数据表是否已创建无法确认。",
            table_creation_uncertain=True,
        )
    return str(table_id)


def _table_url(app_token: str, table_id: str) -> str:
    return f"https://feishu.cn/base/{quote(app_token, safe='')}?table={quote(table_id, safe='')}"


def dispatch_to_feishu_bitable(
    tasks: List[Dict[str, Any]],
    meeting_name: str = "",
    meeting_date: str = "",
) -> Dict[str, Any]:
    """Create a fresh Bitable table for this meeting and write its task rows."""
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN", "").strip()
    if not all((app_id, app_secret, app_token)):
        return {
            "success": False,
            "skipped": True,
            "created": 0,
            "failed": len(tasks),
            "total": len(tasks),
            "table_created": False,
            "error": "飞书多维表格尚未配置；请设置 FEISHU_APP_ID、FEISHU_APP_SECRET 和 FEISHU_BITABLE_APP_TOKEN。",
        }

    try:
        base_name = build_meeting_table_base_name(meeting_name, meeting_date)
        field_specs = _bitable_field_specs()
        field_names = [field["field_name"] for field in field_specs]
        if len(set(field_names)) != len(field_names):
            raise ValueError("FEISHU_FIELD_* 配置中存在重复列名，请检查本机 .env 后重试。")
    except ValueError as exc:
        return {
            "success": False,
            "created": 0,
            "failed": len(tasks),
            "total": len(tasks),
            "table_created": False,
            "error": str(exc),
        }

    try:
        access_token = _get_tenant_access_token(app_id, app_secret)
    except requests.exceptions.RequestException:
        logger.warning("Feishu Bitable authentication request failed.")
        return {"success": False, "created": 0, "failed": len(tasks), "total": len(tasks), "table_created": False, "error": "飞书鉴权请求失败，请检查网络连接。"}
    except RuntimeError as exc:
        return {"success": False, "created": 0, "failed": len(tasks), "total": len(tasks), "table_created": False, "error": str(exc)}

    secrets = [app_id, app_secret, access_token]
    table_name = base_name
    table_id = None
    create_request_started = False
    try:
        # Serialize concurrent calls in this local process, then retry only an
        # explicit name-conflict response from Feishu.
        with _BITABLE_TABLE_CREATE_LOCK:
            for attempt in range(3):
                existing_names = _list_bitable_table_names(app_token, access_token, secrets)
                table_name = _next_table_name(base_name, existing_names)
                create_request_started = True
                try:
                    table_id = _create_bitable_table(
                        app_token, access_token, table_name, field_specs, secrets
                    )
                    break
                except FeishuAPIError as exc:
                    if exc.code == "1254013" and attempt < 2:
                        create_request_started = False
                        continue
                    raise
    except ValueError as exc:
        return {
            "success": False,
            "created": 0,
            "failed": len(tasks),
            "total": len(tasks),
            "table_created": False,
            "table_name": table_name,
            "error": str(exc),
        }
    except requests.exceptions.RequestException:
        logger.warning("Feishu Bitable table creation request failed.")
        return {
            "success": False,
            "created": 0,
            "failed": len(tasks),
            "total": len(tasks),
            "table_created": None if create_request_started else False,
            "table_creation_uncertain": create_request_started,
            "table_name": table_name,
            "error": (
                "建表请求未收到完整响应，飞书中是否已创建无法确认；实际写入 0 条，请先查看 Base 左侧数据表列表。"
                if create_request_started
                else "查询飞书数据表请求失败，请检查网络和应用权限；尚未发起建表或写入。"
            ),
        }
    except FeishuAPIError as exc:
        uncertain = create_request_started and (
            exc.table_creation_uncertain or exc.code is None
        )
        return {
            "success": False,
            "created": 0,
            "failed": len(tasks),
            "total": len(tasks),
            "table_created": None if uncertain else False,
            "table_creation_uncertain": uncertain,
            "table_name": table_name,
            "error": str(exc),
        }

    table_url = _table_url(app_token, table_id)

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
            try:
                _feishu_response_data(response, secrets)
            except FeishuAPIError as exc:
                results.append(
                    {
                        "success": False,
                        "task": task.get("task", ""),
                        "error": str(exc),
                    }
                )
            else:
                results.append({"success": True, "task": task.get("task", "")})
        except (requests.exceptions.RequestException, ValueError, TypeError) as exc:
            results.append({"success": False, "task": task.get("task", ""), "error": "创建记录请求失败，请检查网络或多维表格权限。"})

    created = sum(1 for result in results if result["success"])
    failed = len(results) - created
    logger.info("Feishu Bitable dispatch complete: %d created, %d failed.", created, failed)
    result = {
        "success": failed == 0,
        "created": created,
        "failed": failed,
        "total": len(tasks),
        "table_created": True,
        "table_name": table_name,
        "table_id": table_id,
        "table_url": table_url,
        "fields_created": len(field_specs),
        "items": results,
    }
    if failed:
        result["error"] = f"新表已创建；{created}/{len(tasks)} 条任务写入成功，{failed} 条失败。"
    return result


def _valid_bitable_table_link(bitable_result: Dict[str, Any]) -> str:
    """Return a Base link only when this run fully wrote to its new table."""
    if not bitable_result or bitable_result.get("success") is not True:
        return ""
    link = str(bitable_result.get("table_url", "")).strip()
    parsed = urlparse(link)
    if (
        parsed.scheme == "https"
        and parsed.netloc == "feishu.cn"
        and parsed.path.startswith("/base/")
        and parse_qs(parsed.query).get("table")
    ):
        return link
    return ""


def build_feishu_message(
    tasks: List[Dict[str, Any]],
    meeting_name: str,
    meeting_date: str,
    bitable_result: Dict[str, Any] = None,
) -> str:
    """Build a Chinese meeting summary, optionally including this run's table result."""
    ordered = sorted(tasks, key=lambda item: item.get("priority_score", 0), reverse=True)
    keyword = os.getenv("FEISHU_BOT_KEYWORD", "").strip()
    title = f"会议行动项汇总（{len(ordered)} 项）"
    if keyword:
        title = f"{keyword} {title}"
    lines = [title, f"会议名称：{meeting_name}", f"会议日期：{meeting_date}"]

    if bitable_result is not None:
        table_link = _valid_bitable_table_link(bitable_result)
        if table_link:
            lines.append(f"任务表：{table_link}")
        else:
            created = int(bitable_result.get("created", 0) or 0)
            total = int(bitable_result.get("total", len(ordered)) or 0)
            error = str(bitable_result.get("error", "")).strip()
            status = "多维表格写入未完成" if bitable_result.get("skipped") else "多维表格写入失败"
            status_line = f"{status}：实际写入 {created}/{total} 条"
            if error:
                status_line += f"；{error}"
            lines.append(status_line)

    blocks = ["\n".join(lines)]
    if not ordered:
        blocks.append("本次会议没有提取到待办任务。")
    for index, task in enumerate(ordered, 1):
        review = "；需要人工复核" if task.get("needs_review") else ""
        blocks.append(
            f"{index}. [{_priority_label(task.get('priority_label'))} · "
            f"{task.get('priority_score', '?')}分] "
            f"{task.get('task', '未命名任务')}\n"
            f"负责人：{task.get('owner', '待确认')}；截止：{task.get('deadline', '待确认')}{review}"
        )
    return "\n\n".join(blocks)


def _webhook_signature(secret: str, timestamp: str) -> str:
    sign_string = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(sign_string, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def dispatch_to_feishu_chat(
    tasks: List[Dict[str, Any]],
    meeting_name: str = "",
    meeting_date: str = "",
    bitable_result: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Send a text summary to a Feishu custom-bot webhook."""
    webhook_url = os.getenv("FEISHU_BOT_WEBHOOK_URL", "").strip()
    secret = os.getenv("FEISHU_BOT_SECRET", "").strip()
    if not webhook_url:
        return {
            "success": False,
            "skipped": True,
            "error": "飞书群机器人尚未配置；请设置 FEISHU_BOT_WEBHOOK_URL。",
        }

    try:
        meeting_name, meeting_date = normalize_meeting_metadata(meeting_name, meeting_date)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    message = build_feishu_message(tasks, meeting_name, meeting_date, bitable_result)
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
