from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BotConfig:
    host: str
    port: int
    onebot_ws_urls: list[str]
    onebot_access_token: str
    onebot_http_url: str
    onebot_http_access_token: str
    onebot_http_timeout: float
    expand_forward_messages: bool
    nicknames: list[str]
    superusers: set[str]
    data_dir: Path
    db_path: Path
    group_mode: str
    private_replies: bool
    rules: list[dict[str, Any]]
    reaction_webhook: str
    webhook_timeout: float
    log_level: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        data_dir = Path(os.getenv("QQBOT_DATA_DIR", "./data")).expanduser()
        db_path = Path(os.getenv("QQBOT_DB_PATH", str(data_dir / "messages.db"))).expanduser()
        group_mode = os.getenv("QQBOT_GROUP_MODE", "mention").strip().lower()
        if group_mode not in {"mention", "all", "none"}:
            raise ValueError("QQBOT_GROUP_MODE must be one of: mention, all, none")

        rules_raw = os.getenv("QQBOT_RULES_JSON", "[]")
        try:
            rules = json.loads(rules_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid QQBOT_RULES_JSON: {exc}") from exc
        if not isinstance(rules, list):
            raise ValueError("QQBOT_RULES_JSON must be a JSON list")

        return cls(
            host=os.getenv("QQBOT_HOST", "0.0.0.0"),
            port=int(os.getenv("QQBOT_PORT", "8080")),
            onebot_ws_urls=_csv(os.getenv("QQBOT_ONEBOT_WS_URLS")),
            onebot_access_token=os.getenv("QQBOT_ONEBOT_ACCESS_TOKEN", ""),
            onebot_http_url=os.getenv("QQBOT_ONEBOT_HTTP_URL", "").rstrip("/"),
            onebot_http_access_token=os.getenv(
                "QQBOT_ONEBOT_HTTP_ACCESS_TOKEN",
                os.getenv("QQBOT_ONEBOT_ACCESS_TOKEN", ""),
            ),
            onebot_http_timeout=float(os.getenv("QQBOT_ONEBOT_HTTP_TIMEOUT", "10")),
            expand_forward_messages=_bool("QQBOT_EXPAND_FORWARD_MESSAGES", True),
            nicknames=_csv(os.getenv("QQBOT_NICKNAMES")) or ["qqbot"],
            superusers=set(_csv(os.getenv("QQBOT_SUPERUSERS"))),
            data_dir=data_dir,
            db_path=db_path,
            group_mode=group_mode,
            private_replies=_bool("QQBOT_PRIVATE_REPLIES", True),
            rules=rules,
            reaction_webhook=os.getenv("QQBOT_REACTION_WEBHOOK", ""),
            webhook_timeout=float(os.getenv("QQBOT_WEBHOOK_TIMEOUT", "5")),
            log_level=os.getenv("QQBOT_LOG_LEVEL", "INFO"),
        )


_config: BotConfig | None = None


def load_config() -> BotConfig:
    global _config
    if _config is None:
        _config = BotConfig.from_env()
    return _config


def set_config(config: BotConfig) -> None:
    global _config
    _config = config
