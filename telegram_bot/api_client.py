from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BackendClient:
    """Клиент к backend API (POST /v1/chat/handle, POST /v1/chat/reset)."""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def handle_chat(
        self,
        user_id: str,
        chat_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Отправляет сообщение в backend, возвращает ответ с полем text (и опционально type)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/handle",
                json={"user_id": user_id, "chat_id": chat_id, "text": text},
            )
            resp.raise_for_status()
            data = resp.json()
            return data

    async def reset_chat(self, *, chat_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        """Сбрасывает сессию по chat_id или session_id."""
        payload: dict[str, str] = {}
        if chat_id is not None:
            payload["chat_id"] = chat_id
        if session_id is not None:
            payload["session_id"] = session_id
        if not payload:
            raise ValueError("Нужно указать chat_id или session_id")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/reset",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
