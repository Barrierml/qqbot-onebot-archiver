from __future__ import annotations

from typing import Any

import aiohttp


class OneBotApiError(RuntimeError):
    pass


class OneBotHttpClient:
    def __init__(self, base_url: str, access_token: str = "", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            raise OneBotApiError("OneBot HTTP URL is not configured")

        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        url = f"{self.base_url}/{action.lstrip('/')}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload or {}, headers=headers) as response:
                text = await response.text()
                if response.status >= 400:
                    raise OneBotApiError(f"{action} failed with HTTP {response.status}: {text[:300]}")
                try:
                    body = await response.json()
                except Exception as exc:
                    raise OneBotApiError(f"{action} returned non-JSON response: {text[:300]}") from exc

        if body.get("status") != "ok" or body.get("retcode") not in {0, None}:
            raise OneBotApiError(f"{action} failed: {body}")
        data = body.get("data")
        return data if isinstance(data, dict) else {"data": data}

    async def get_forward_msg(self, forward_id: str) -> list[dict[str, Any]]:
        data = await self.call("get_forward_msg", {"id": forward_id})
        messages = data.get("messages")
        return messages if isinstance(messages, list) else []
