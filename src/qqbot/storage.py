from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ArchivedMessage:
    message_id: str
    self_id: str
    message_type: str
    sub_type: str
    user_id: str
    group_id: str | None
    plain_text: str
    raw_message: str
    segments: list[dict[str, Any]]
    sender: dict[str, Any]
    event: dict[str, Any]
    received_at: str


class MessageStore:
    def __init__(self, path: Path):
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    self_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    sub_type TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT,
                    plain_text TEXT NOT NULL,
                    raw_message TEXT NOT NULL,
                    segments_json TEXT NOT NULL,
                    sender_json TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    UNIQUE(self_id, message_id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_received_at
                    ON messages(received_at);
                CREATE INDEX IF NOT EXISTS idx_messages_user
                    ON messages(user_id, received_at);
                CREATE INDEX IF NOT EXISTS idx_messages_group
                    ON messages(group_id, received_at);

                CREATE TABLE IF NOT EXISTS reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_row_id INTEGER,
                    rule_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    response TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(message_row_id) REFERENCES messages(id)
                );
                """
            )
            await db.commit()

    async def save_message(self, message: ArchivedMessage) -> int:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO messages (
                    message_id, self_id, message_type, sub_type, user_id,
                    group_id, plain_text, raw_message, segments_json,
                    sender_json, event_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.self_id,
                    message.message_type,
                    message.sub_type,
                    message.user_id,
                    message.group_id,
                    message.plain_text,
                    message.raw_message,
                    json.dumps(message.segments, ensure_ascii=False),
                    json.dumps(message.sender, ensure_ascii=False),
                    json.dumps(message.event, ensure_ascii=False),
                    message.received_at,
                ),
            )
            await db.commit()
            async with db.execute(
                "SELECT id FROM messages WHERE self_id = ? AND message_id = ?",
                (message.self_id, message.message_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("message save failed")
                return int(row[0])

    async def save_reaction(
        self,
        message_row_id: int | None,
        rule_name: str,
        action: str,
        status: str,
        response: str | None = None,
        error: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO reactions (
                    message_row_id, rule_name, action, response, status, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_row_id, rule_name, action, response, status, error, utc_now()),
            )
            await db.commit()

    async def recent_messages(self, limit: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 50))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT message_id, message_type, user_id, group_id, plain_text, received_at
                FROM messages
                ORDER BY received_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

