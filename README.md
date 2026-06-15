# qqbot

Standalone QQ/OneBot message archiver and reaction bot.

It is extracted from the QQ-facing part of `Barrierml/my-agent`, but keeps only:

- read OneBot v11 messages from NapCat or another OneBot implementation
- save every message into SQLite
- expand merged forward messages through OneBot `get_forward_msg`
- react with built-in commands, keyword rules, or an optional webhook

## Quick Start

```bash
cd /Users/bytedance/qqbot
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'

export QQBOT_ONEBOT_WS_URLS='ws://172.17.66.6:3001?access_token=<token>'
export QQBOT_SUPERUSERS='1196768261'
qqbot
```

## Configuration

All runtime configuration uses environment variables.

| Variable | Default | Description |
|---|---|---|
| `QQBOT_HOST` | `0.0.0.0` | NoneBot server host |
| `QQBOT_PORT` | `8080` | NoneBot server port |
| `QQBOT_ONEBOT_WS_URLS` | empty | Comma-separated reverse/client WebSocket URLs |
| `QQBOT_ONEBOT_ACCESS_TOKEN` | empty | OneBot access token when not embedded in URL |
| `QQBOT_ONEBOT_HTTP_URL` | empty | OneBot HTTP API base URL, e.g. `http://napcat:3000` |
| `QQBOT_ONEBOT_HTTP_ACCESS_TOKEN` | `QQBOT_ONEBOT_ACCESS_TOKEN` | OneBot HTTP API token |
| `QQBOT_ONEBOT_HTTP_TIMEOUT` | `10` | OneBot HTTP API timeout seconds |
| `QQBOT_EXPAND_FORWARD_MESSAGES` | `true` | Expand `[CQ:forward,id=...]` messages and archive child messages |
| `QQBOT_NICKNAMES` | `qqbot` | Comma-separated bot nicknames |
| `QQBOT_SUPERUSERS` | empty | Comma-separated QQ IDs allowed to run admin commands |
| `QQBOT_DATA_DIR` | `./data` | SQLite and runtime data directory |
| `QQBOT_DB_PATH` | `$QQBOT_DATA_DIR/messages.db` | SQLite database path |
| `QQBOT_GROUP_MODE` | `mention` | `mention`, `all`, or `none` |
| `QQBOT_PRIVATE_REPLIES` | `true` | Enable private chat reactions |
| `QQBOT_RULES_JSON` | `[]` | Keyword rules JSON |
| `QQBOT_REACTION_WEBHOOK` | empty | Optional HTTP webhook for custom reactions |
| `QQBOT_WEBHOOK_TIMEOUT` | `5` | Webhook timeout seconds |

Example rules:

```bash
export QQBOT_RULES_JSON='[
  {"name":"hello","contains":"你好","reply":"你好，我在。"},
  {"name":"help","prefix":"/help","reply":"可用命令：/ping /recent 10"}
]'
```

Webhook request body:

```json
{
  "message": {"plain_text": "...", "message_type": "private"},
  "event": {"raw OneBot event": "..."}
}
```

Webhook response can be:

```json
{"reply": "text to send"}
```

## Built-In Commands

- `/ping` replies `pong`
- `/recent [n]` replies with recent saved messages; superuser only

## Docker

```bash
docker build -t qqbot:0.1.4 .
docker compose -f deploy/docker-compose.yml up -d
```
