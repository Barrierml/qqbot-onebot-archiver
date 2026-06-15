from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger
from starlette.responses import HTMLResponse

from qqbot.config import load_config
from qqbot.onebot_api import OneBotHttpClient
from qqbot.reactions import ReactionEngine
from qqbot.storage import ArchivedMessage, MessageStore, utc_now


config = load_config()
store = MessageStore(config.db_path)
engine = ReactionEngine(config, store)
onebot_http = OneBotHttpClient(
    config.onebot_http_url,
    config.onebot_http_access_token,
    config.onebot_http_timeout,
)
driver = get_driver()


@driver.on_startup
async def init_store() -> None:
    await store.init()
    logger.info(f"qqbot message store initialized: {config.db_path}")


class HttpEventContext:
    def __init__(self, event: dict[str, Any]):
        self.event = event

    def is_tome(self) -> bool:
        if self.event.get("message_type") != "group":
            return False
        self_id = str(self.event.get("self_id") or "")
        for segment in _event_segments(self.event):
            if segment.get("type") == "at" and str(segment.get("data", {}).get("qq") or "") == self_id:
                return True
        plain_text = _plain_text_from_event(self.event)
        return any(name and name in plain_text for name in config.nicknames)


if hasattr(driver, "server_app"):
    app = driver.server_app

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(_render_index())

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "qqbot",
            "db_path": str(config.db_path),
            "group_mode": config.group_mode,
            "webhook_enabled": bool(config.reaction_webhook),
            "onebot_http_enabled": onebot_http.enabled,
            "expand_forward_messages": config.expand_forward_messages,
            "rules": len(config.rules),
        }

    @app.get("/api/messages")
    async def api_messages(limit: int = 50) -> dict[str, Any]:
        return {"ok": True, "messages": await store.recent_messages(limit)}

    @app.get("/api/reactions")
    async def api_reactions(limit: int = 50) -> dict[str, Any]:
        return {"ok": True, "reactions": await store.recent_reactions(limit)}

    @app.get("/messages")
    async def messages_page(limit: int = 50) -> HTMLResponse:
        messages = await store.recent_messages(limit)
        reactions = await store.recent_reactions(20)
        return HTMLResponse(_render_messages(messages, reactions))

    async def ingest_http_event(payload: dict[str, Any]) -> dict[str, Any]:
        archived = _archive_event_payload(payload)
        row_id = await store.save_message(archived)
        expanded_count = await _expand_and_store_forward_messages(payload, archived.message_id, row_id)
        reactions = await engine.evaluate(archived, HttpEventContext(payload))
        returned = []
        for reaction in reactions:
            returned.append({"name": reaction.name, "reply": reaction.reply, "source": reaction.source})
            await store.save_reaction(row_id, reaction.name, "reply", "returned", response=reaction.reply)
        return {
            "ok": True,
            "message_row_id": row_id,
            "forward_messages": expanded_count,
            "reactions": returned,
        }

    @app.post("/")
    async def ingest_root(payload: dict[str, Any]) -> dict[str, Any]:
        return await ingest_http_event(payload)

    @app.post("/event")
    async def ingest_event(payload: dict[str, Any]) -> dict[str, Any]:
        return await ingest_http_event(payload)

    @app.post("/onebot")
    async def ingest_onebot(payload: dict[str, Any]) -> dict[str, Any]:
        return await ingest_http_event(payload)

    @app.post("/onebot/v11")
    async def ingest_onebot_v11(payload: dict[str, Any]) -> dict[str, Any]:
        return await ingest_http_event(payload)


def _event_dict(event: MessageEvent) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    if hasattr(event, "dict"):
        return event.dict()
    return {}


def _html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f7f4; color: #191917; }}
    header {{ padding: 18px 24px; border-bottom: 1px solid #ddd9cf; background: #ffffff; position: sticky; top: 0; }}
    main {{ padding: 20px 24px 40px; max-width: 1180px; }}
    a {{ color: #175ddc; text-decoration: none; }}
    .meta {{ color: #6b665c; font-size: 12px; }}
    .grid {{ display: grid; gap: 14px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #ddd9cf; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #ebe7de; vertical-align: top; text-align: left; }}
    th {{ background: #f0eee8; font-weight: 650; white-space: nowrap; }}
    td.message {{ max-width: 520px; white-space: pre-wrap; word-break: break-word; }}
    .pill {{ display: inline-block; padding: 2px 7px; border: 1px solid #cfc8b8; border-radius: 999px; font-size: 12px; background: #faf9f4; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #151515; color: #eee; }}
      header, table {{ background: #1f1f1f; border-color: #3a3a3a; }}
      th {{ background: #2a2a2a; }}
      th, td {{ border-color: #343434; }}
      .meta {{ color: #aaa; }}
      .pill {{ background: #242424; border-color: #555; }}
    }}
  </style>
</head>
<body>
  <header>
    <strong>qqbot</strong>
    <span class="meta"> / <a href="/messages">messages</a> / <a href="/healthz">healthz</a> / <a href="/api/messages">api</a></span>
  </header>
  <main>{body}</main>
</body>
</html>"""


def _render_index() -> str:
    body = """
    <div class="grid">
      <p>QQ/OneBot message archiver and reaction bot is running.</p>
      <p><a href="/messages">查看最近聊天记录</a></p>
    </div>
    """
    return _page("qqbot", body)


def _render_messages(messages: list[dict[str, Any]], reactions: list[dict[str, Any]]) -> str:
    message_rows = "\n".join(
        f"""<tr>
          <td class="meta">{_html_escape(row.get("received_at"))}</td>
          <td><span class="pill">{_html_escape(row.get("message_type"))}</span></td>
          <td>{_html_escape(row.get("group_id") or row.get("user_id"))}</td>
          <td class="message">{_html_escape(row.get("plain_text"))}</td>
        </tr>"""
        for row in messages
    ) or '<tr><td colspan="4" class="meta">暂无消息</td></tr>'
    reaction_rows = "\n".join(
        f"""<tr>
          <td class="meta">{_html_escape(row.get("created_at"))}</td>
          <td>{_html_escape(row.get("rule_name"))}</td>
          <td>{_html_escape(row.get("status"))}</td>
          <td class="message">{_html_escape(row.get("response") or row.get("error") or "")}</td>
        </tr>"""
        for row in reactions
    ) or '<tr><td colspan="4" class="meta">暂无反应记录</td></tr>'
    body = f"""
    <section>
      <h2>最近消息</h2>
      <table>
        <thead><tr><th>时间</th><th>类型</th><th>来源</th><th>内容</th></tr></thead>
        <tbody>{message_rows}</tbody>
      </table>
    </section>
    <section style="margin-top: 28px;">
      <h2>最近反应</h2>
      <table>
        <thead><tr><th>时间</th><th>规则</th><th>状态</th><th>响应/错误</th></tr></thead>
        <tbody>{reaction_rows}</tbody>
      </table>
    </section>
    """
    return _page("qqbot messages", body)


def _event_segments(event_data: dict[str, Any]) -> list[dict[str, Any]]:
    message = event_data.get("message")
    if isinstance(message, list):
        return [{"type": str(seg.get("type", "")), "data": dict(seg.get("data") or {})} for seg in message]
    return []


def _forward_ids_from_event(event_data: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for segment in _event_segments(event_data):
        if segment.get("type") == "forward":
            forward_id = segment.get("data", {}).get("id")
            if forward_id:
                ids.append(str(forward_id))

    raw = event_data.get("raw_message")
    if isinstance(raw, str):
        ids.extend(re.findall(r"\[CQ:forward,[^\]]*id=([^,\]]+)", raw))

    unique = []
    seen = set()
    for forward_id in ids:
        if forward_id not in seen:
            unique.append(forward_id)
            seen.add(forward_id)
    return unique


def _plain_text_from_event(event_data: dict[str, Any]) -> str:
    raw = event_data.get("raw_message")
    if isinstance(raw, str):
        return raw.strip()
    parts = []
    for segment in _event_segments(event_data):
        if segment.get("type") == "text":
            parts.append(str(segment.get("data", {}).get("text") or ""))
    return "".join(parts).strip()


def _segments(event: MessageEvent) -> list[dict[str, Any]]:
    segments = []
    for segment in event.get_message():
        segments.append({"type": segment.type, "data": dict(segment.data)})
    return segments


def _archive_event_payload(event_data: dict[str, Any]) -> ArchivedMessage:
    message_id = str(event_data.get("message_id") or "")
    if not message_id:
        message_id = f'{event_data.get("time", "")}:{event_data.get("user_id", "")}:{hash(str(event_data.get("message")))}'

    group_id = event_data.get("group_id")
    sender = event_data.get("sender") if isinstance(event_data.get("sender"), dict) else {}
    raw_message = event_data.get("raw_message")
    if not isinstance(raw_message, str):
        raw_message = str(event_data.get("message") or "")

    return ArchivedMessage(
        message_id=message_id,
        self_id=str(event_data.get("self_id") or ""),
        message_type=str(event_data.get("message_type") or ""),
        sub_type=str(event_data.get("sub_type") or ""),
        user_id=str(event_data.get("user_id") or ""),
        group_id=str(group_id) if group_id is not None else None,
        plain_text=_plain_text_from_event(event_data),
        raw_message=raw_message,
        segments=_event_segments(event_data),
        sender=sender,
        event=event_data,
        received_at=_received_at_from_event(event_data),
    )


def _received_at_from_event(event_data: dict[str, Any]) -> str:
    timestamp = event_data.get("time")
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    return utc_now()


def _forward_child_event(
    message: dict[str, Any],
    forward_id: str,
    parent_message_id: str,
) -> dict[str, Any]:
    event = dict(message)
    event["message_id"] = f"forward:{forward_id}:{message.get('message_id') or message.get('message_seq') or hash(str(message))}"
    event.setdefault("post_type", "message")
    event["qqbot_archive"] = {
        "source": "forward",
        "forward_id": forward_id,
        "parent_message_id": parent_message_id,
    }
    return event


async def _expand_and_store_forward_messages(
    event_data: dict[str, Any],
    parent_message_id: str,
    parent_row_id: int | None,
) -> int:
    if not config.expand_forward_messages or not onebot_http.enabled:
        return 0

    saved = 0
    for forward_id in _forward_ids_from_event(event_data):
        try:
            messages = await onebot_http.get_forward_msg(forward_id)
        except Exception as exc:
            logger.exception("forward message expansion failed: %s", forward_id)
            await store.save_reaction(
                parent_row_id,
                "forward_expand",
                "get_forward_msg",
                "error",
                error=f"{forward_id}: {exc}",
            )
            continue

        for message in messages:
            if not isinstance(message, dict):
                continue
            archived = _archive_event_payload(_forward_child_event(message, forward_id, parent_message_id))
            await store.save_message(archived)
            saved += 1

        await store.save_reaction(
            parent_row_id,
            "forward_expand",
            "get_forward_msg",
            "saved",
            response=f"{forward_id}: {saved} messages",
        )
    return saved


def _archive_message(event: MessageEvent) -> ArchivedMessage:
    event_data = _event_dict(event)
    message_id = str(getattr(event, "message_id", "") or event_data.get("message_id") or "")
    if not message_id:
        message_id = f'{event_data.get("time", "")}:{event_data.get("user_id", "")}:{hash(str(event.get_message()))}'

    group_id = str(getattr(event, "group_id", "")) if isinstance(event, GroupMessageEvent) else None
    message_type = str(getattr(event, "message_type", event_data.get("message_type", "")) or "")
    sub_type = str(getattr(event, "sub_type", event_data.get("sub_type", "")) or "")
    user_id = str(getattr(event, "user_id", event_data.get("user_id", "")) or "")
    self_id = str(getattr(event, "self_id", event_data.get("self_id", "")) or "")
    sender = event_data.get("sender") if isinstance(event_data.get("sender"), dict) else {}

    return ArchivedMessage(
        message_id=message_id,
        self_id=self_id,
        message_type=message_type,
        sub_type=sub_type,
        user_id=user_id,
        group_id=group_id,
        plain_text=event.get_plaintext().strip(),
        raw_message=str(event.get_message()),
        segments=_segments(event),
        sender=sender,
        event=event_data,
        received_at=utc_now(),
    )


message_handler = on_message(priority=10, block=False)


@message_handler.handle()
async def handle_message(bot: Bot, event: MessageEvent) -> None:
    archived = _archive_message(event)
    row_id = await store.save_message(archived)
    await _expand_and_store_forward_messages(_event_dict(event), archived.message_id, row_id)
    logger.info(
        "saved message id=%s type=%s user=%s group=%s",
        archived.message_id,
        archived.message_type,
        archived.user_id,
        archived.group_id,
    )

    try:
        reactions = await engine.evaluate(archived, event)
    except Exception as exc:
        logger.exception("reaction evaluation failed")
        await store.save_reaction(row_id, "reaction_error", "evaluate", "error", error=str(exc))
        return

    for reaction in reactions:
        try:
            await bot.send(event, reaction.reply)
            await store.save_reaction(row_id, reaction.name, "reply", "sent", response=reaction.reply)
            logger.info("sent reaction rule=%s source=%s", reaction.name, reaction.source)
        except Exception as exc:
            logger.exception("reaction send failed")
            await store.save_reaction(
                row_id,
                reaction.name,
                "reply",
                "error",
                response=reaction.reply,
                error=str(exc),
            )
