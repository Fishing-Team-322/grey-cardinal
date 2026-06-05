"""Тонкий клиент к OpenAI-совместимому Chat Completions API (через httpx).

Proxy: set LLM_PROXY=http://user:pass@host:port in .env to route LLM traffic
through a proxy (needed when the server's IP is geo-blocked by the provider).
"""

from __future__ import annotations

import os
import httpx


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        proxy: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # Explicit proxy > LLM_PROXY env var > system HTTPS_PROXY
        self._proxy = proxy or os.getenv("LLM_PROXY") or None

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Вернуть текстовый content первого choice."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        client_kwargs: dict = {"timeout": self._timeout}
        if self._proxy:
            client_kwargs["proxy"] = self._proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]
