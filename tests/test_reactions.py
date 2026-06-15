from pathlib import Path

import pytest

from qqbot.config import BotConfig
from qqbot.reactions import ReactionEngine
from qqbot.storage import ArchivedMessage, MessageStore, utc_now


class DummyPrivateEvent:
    pass


class DummyGroupMentionEvent:
    def is_tome(self):
        return True


def make_config(tmp_path: Path, **overrides) -> BotConfig:
    values = dict(
        host="127.0.0.1",
        port=8080,
        onebot_ws_urls=[],
        onebot_access_token="",
        nicknames=["qqbot"],
        superusers={"1"},
        data_dir=tmp_path,
        db_path=tmp_path / "messages.db",
        group_mode="mention",
        private_replies=True,
        rules=[],
        reaction_webhook="",
        webhook_timeout=1.0,
        log_level="INFO",
    )
    values.update(overrides)
    return BotConfig(**values)


def make_message(text: str, user_id: str = "1", message_type: str = "private") -> ArchivedMessage:
    return ArchivedMessage(
        message_id=f"m-{hash((text, user_id, message_type))}",
        self_id="bot",
        message_type=message_type,
        sub_type="",
        user_id=user_id,
        group_id="g1" if message_type == "group" else None,
        plain_text=text,
        raw_message=text,
        segments=[{"type": "text", "data": {"text": text}}],
        sender={},
        event={},
        received_at=utc_now(),
    )


@pytest.mark.asyncio
async def test_ping_reply(tmp_path):
    cfg = make_config(tmp_path)
    store = MessageStore(cfg.db_path)
    await store.init()
    engine = ReactionEngine(cfg, store)

    reactions = await engine.evaluate(make_message("/ping"), DummyPrivateEvent())

    assert [r.reply for r in reactions] == ["pong"]


@pytest.mark.asyncio
async def test_keyword_rule(tmp_path):
    cfg = make_config(tmp_path, rules=[{"name": "hello", "contains": "你好", "reply": "你好，我在。"}])
    store = MessageStore(cfg.db_path)
    await store.init()
    engine = ReactionEngine(cfg, store)

    reactions = await engine.evaluate(make_message("你好呀"), DummyPrivateEvent())

    assert reactions[0].name == "hello"
    assert reactions[0].reply == "你好，我在。"


@pytest.mark.asyncio
async def test_group_requires_mention_by_default(tmp_path):
    cfg = make_config(tmp_path, rules=[{"name": "hello", "contains": "hi", "reply": "hi"}])
    store = MessageStore(cfg.db_path)
    await store.init()
    engine = ReactionEngine(cfg, store)

    class NotMentioned:
        def is_tome(self):
            return False

    assert await engine.evaluate(make_message("hi", message_type="group"), NotMentioned()) == []
    assert (await engine.evaluate(make_message("hi", message_type="group"), DummyGroupMentionEvent()))[0].reply == "hi"


@pytest.mark.asyncio
async def test_recent_is_superuser_only(tmp_path):
    cfg = make_config(tmp_path)
    store = MessageStore(cfg.db_path)
    await store.init()
    saved = make_message("hello")
    await store.save_message(saved)
    engine = ReactionEngine(cfg, store)

    denied = await engine.evaluate(make_message("/recent", user_id="2"), DummyPrivateEvent())
    allowed = await engine.evaluate(make_message("/recent 1", user_id="1"), DummyPrivateEvent())

    assert denied[0].reply == "permission denied"
    assert "hello" in allowed[0].reply

