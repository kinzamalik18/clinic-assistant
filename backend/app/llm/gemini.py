"""Google Gemini API client (Generative Language REST API)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import LLMError, Message
from app.llm.sse import iter_sse_json

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: httpx.AsyncClient, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Gemini API key is empty")
        self._client = client
        self._headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        self._model = model

    def _body(
        self, system: str, messages: list[Message], temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }

    @staticmethod
    def _text(data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMError(f"Gemini returned no answer ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

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
            body["generationConfig"]["responseMimeType"] = "application/json"
        url = f"{BASE_URL}/models/{self._model}:generateContent"
        try:
            response = await self._client.post(url, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise LLMError(f"Gemini returned HTTP {response.status_code}")
        text = self._text(response.json())
        if not text.strip():
            raise LLMError("Gemini returned an empty answer")
        return text

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        body = self._body(system, messages, temperature, max_tokens)
        url = f"{BASE_URL}/models/{self._model}:streamGenerateContent"
        try:
            async with self._client.stream(
                "POST", url, params={"alt": "sse"}, headers=self._headers, json=body
            ) as response:
                if response.status_code != 200:
                    raise LLMError(f"Gemini returned HTTP {response.status_code}")
                async for data in iter_sse_json(response):
                    if not data.get("candidates") and not data.get("promptFeedback"):
                        continue  # e.g. a trailing chunk that only carries usage metadata
                    text = self._text(data)
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini stream failed: {type(exc).__name__}") from exc
