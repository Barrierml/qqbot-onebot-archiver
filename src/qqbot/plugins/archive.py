from __future__ import annotations

from typing import Any

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger

from qqbot.config import load_config
from qqbot.reactions import ReactionEngine
from qqbot.storage import ArchivedMessage, MessageStore, utc_now


config = load_config()
store = MessageStore(config.db_path)
engine = ReactionEngine(config, store)
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

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "qqbot",
            "db_path": str(config.db_path),
            "group_mode": config.group_mode,
            "webhook_enabled": bool(config.reaction_webhook),
            "rules": len(config.rules),
        }

    async def ingest_http_event(payload: dict[str, Any]) -> dict[str, Any]:
        archived = _archive_event_payload(payload)
        row_id = await store.save_message(archived)
        reactions = await engine.evaluate(archived, HttpEventContext(payload))
        returned = []
        for reaction in reactions:
            returned.append({"name": reaction.name, "reply": reaction.reply, "source": reaction.source})
            await store.save_reaction(row_id, reaction.name, "reply", "returned", response=reaction.reply)
        return {"ok": True, "message_row_id": row_id, "reactions": returned}

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


def _event_segments(event_data: dict[str, Any]) -> list[dict[str, Any]]:
    message = event_data.get("message")
    if isinstance(message, list):
        return [{"type": str(seg.get("type", "")), "data": dict(seg.get("data") or {})} for seg in message]
    return []


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
        received_at=utc_now(),
    )


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
