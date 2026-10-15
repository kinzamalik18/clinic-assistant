"""Groq client (OpenAI-compatible chat completions API)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import LLMError, Message
from app.llm.sse import iter_sse_json

URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    name = "groq"

    def __init__(self, client: httpx.AsyncClient, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Groq API key is empty")
        self._client = client
        self._headers = {"authorization": f"Bearer {api_key}"}
        self._model = model

    def _body(
        self, system: str, messages: list[Message], temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    async def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        body = self._body(system, messages, temperature, max_tokens)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            response = await self._client.post(URL, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Groq request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise LLMError(f"Groq returned HTTP {response.status_code}")
        try:
            text = response.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq returned an unexpected response shape") from exc
        if not text.strip():
            raise LLMError("Groq returned an empty answer")
        return str(text)

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        body = self._body(system, messages, temperature, max_tokens)
        body["stream"] = True
        try:
            async with self._client.stream(
                "POST", URL, headers=self._headers, json=body
            ) as response:
                if response.status_code != 200:
                    raise LLMError(f"Groq returned HTTP {response.status_code}")
                async for data in iter_sse_json(response):
                    choices = data.get("choices") or []
                    if choices:
                        text = (choices[0].get("delta") or {}).get("content")
                        if text:
                            yield str(text)
        except httpx.HTTPError as exc:
            raise LLMError(f"Groq stream failed: {type(exc).__name__}") from exc
