"""Google Gemini API client (Generative Language REST API)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import LLMError, Message
from app.llm.errors import http_error
from app.llm.sse import iter_sse_json

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Thinking tokens count toward maxOutputTokens, and an answer cut off mid-thought comes
# back empty. Thinking models get this much room on top of the answer's own budget.
THINKING_HEADROOM = 2048


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: httpx.AsyncClient, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Gemini API key is empty")
        self._client = client
        self._key = api_key
        self._headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        self._model = model
        self._thinks = model.startswith(("gemini-2.5", "gemini-3"))
        # Gemini 3 models take a thinking level; "low" keeps short replies fast.
        self._thinking_level = "low" if model.startswith("gemini-3") else None

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
            "generationConfig": self._generation_config(temperature, max_tokens),
        }

    def _generation_config(self, temperature: float, max_tokens: int) -> dict[str, Any]:
        config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens + (THINKING_HEADROOM if self._thinks else 0),
        }
        if self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        return config

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
            raise LLMError(f"Gemini request failed: {type(exc).__name__}", transient=True) from exc
        if response.status_code != 200:
            raise await http_error("Gemini", response, self._key)
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
                    raise await http_error("Gemini", response, self._key)
                async for data in iter_sse_json(response):
                    if not data.get("candidates") and not data.get("promptFeedback"):
                        continue  # e.g. a trailing chunk that only carries usage metadata
                    text = self._text(data)
                    if text:
                        yield text
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini stream failed: {type(exc).__name__}", transient=True) from exc
