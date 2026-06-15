from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import BotConfig
from .storage import ArchivedMessage, MessageStore


@dataclass(frozen=True)
class Reaction:
    name: str
    reply: str
    source: str = "rule"


class ReactionEngine:
    def __init__(self, config: BotConfig, store: MessageStore):
        self.config = config
        self.store = store

    async def evaluate(self, message: ArchivedMessage, event: Any) -> list[Reaction]:
        if not self._should_react(message, event):
            return []

        text = message.plain_text.strip()
        reactions: list[Reaction] = []

        command_reaction = await self._command_reaction(text, message)
        if command_reaction:
            reactions.append(command_reaction)

        if not reactions:
            rule_reaction = self._keyword_reaction(text)
            if rule_reaction:
                reactions.append(rule_reaction)

        if not reactions:
            webhook_reaction = await self._webhook_reaction(message)
            if webhook_reaction:
                reactions.append(webhook_reaction)

        return reactions

    def _should_react(self, message: ArchivedMessage, event: Any) -> bool:
        if message.message_type == "private":
            return self.config.private_replies
        if message.message_type == "group":
            if self.config.group_mode == "all":
                return True
            if self.config.group_mode == "none":
                return False
            is_tome = getattr(event, "is_tome", lambda: False)
            try:
                return bool(is_tome())
            except Exception:
                return False
        return False

    async def _command_reaction(self, text: str, message: ArchivedMessage) -> Reaction | None:
        lowered = text.lower()
        if lowered == "/ping":
            return Reaction(name="ping", reply="pong", source="builtin")

        if lowered.startswith("/recent"):
            if message.user_id not in self.config.superusers:
                return Reaction(name="recent_denied", reply="permission denied", source="builtin")
            parts = text.split()
            limit = 10
            if len(parts) > 1 and parts[1].isdigit():
                limit = int(parts[1])
            rows = await self.store.recent_messages(limit)
            if not rows:
                return Reaction(name="recent", reply="no messages saved", source="builtin")
            lines = []
            for row in rows:
                target = row["group_id"] or row["user_id"]
                body = row["plain_text"] or row["message_id"]
                lines.append(f'{row["received_at"]} {row["message_type"]}:{target} {body[:80]}')
            return Reaction(name="recent", reply="\n".join(lines), source="builtin")

        return None

    def _keyword_reaction(self, text: str) -> Reaction | None:
        for raw_rule in self.config.rules:
            if not isinstance(raw_rule, dict):
                continue
            name = str(raw_rule.get("name") or "keyword")
            reply = raw_rule.get("reply")
            if not reply:
                continue
            contains = raw_rule.get("contains")
            prefix = raw_rule.get("prefix")
            exact = raw_rule.get("exact")
            if exact is not None and text == str(exact):
                return Reaction(name=name, reply=str(reply))
            if prefix is not None and text.startswith(str(prefix)):
                return Reaction(name=name, reply=str(reply))
            if contains is not None and str(contains) in text:
                return Reaction(name=name, reply=str(reply))
        return None

    async def _webhook_reaction(self, message: ArchivedMessage) -> Reaction | None:
        if not self.config.reaction_webhook:
            return None
        import aiohttp

        payload = {"message": message.__dict__, "event": message.event}
        timeout = aiohttp.ClientTimeout(total=self.config.webhook_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.config.reaction_webhook, json=payload) as response:
                if response.status == 204:
                    return None
                response.raise_for_status()
                data = await response.json()
        reply = data.get("reply") if isinstance(data, dict) else None
        if not reply:
            return None
        return Reaction(name="webhook", reply=str(reply), source="webhook")
