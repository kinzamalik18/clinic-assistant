"""Provider tests against mocked HTTP. No real API calls are made."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.llm.base import LLMError, Message
from app.llm.fallback import FallbackProvider
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider

pytestmark = pytest.mark.anyio

USER = [Message(role="user", content="When are you open?")]


def client_with(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def sse(*events: object) -> bytes:
    return "".join(
        f"data: {json.dumps(e) if not isinstance(e, str) else e}\n\n" for e in events
    ).encode()


async def test_gemini_complete_sends_key_in_header_and_maps_roles() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["x-goog-api-key"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "We open at 8."}]}}]}
        )

    async with client_with(httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(client, "test-key", "gemini-test")
        history = [*USER, Message(role="assistant", content="Hi"), *USER]
        text = await provider.complete("system prompt", history, json_mode=True)

    assert text == "We open at 8."
    assert seen["key"] == "test-key"
    assert "test-key" not in str(seen["url"])
    body = seen["body"]
    assert isinstance(body, dict)
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


async def test_gemini_error_status_raises_without_leaking_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    async with client_with(httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(client, "secret-key", "gemini-test")
        with pytest.raises(LLMError) as info:
            await provider.complete("s", USER)
    assert "429" in str(info.value)
    assert "secret-key" not in str(info.value)


async def test_gemini_blocked_prompt_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    async with client_with(httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError, match="SAFETY"):
            await GeminiProvider(client, "k", "m").complete("s", USER)


async def test_gemini_stream_joins_pieces_and_skips_metadata_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["alt"] == "sse"
        body = sse(
            {"candidates": [{"content": {"parts": [{"text": "We open "}]}}]},
            {"candidates": [{"content": {"parts": [{"text": "at 8."}]}}]},
            {"usageMetadata": {"totalTokenCount": 10}},
        )
        return httpx.Response(200, content=body)

    async with client_with(httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(client, "k", "m")
        pieces = [p async for p in provider.stream("s", USER)]
    assert "".join(pieces) == "We open at 8."


async def test_groq_complete_and_json_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gk"
        body = json.loads(request.content)
        assert body["messages"][0] == {"role": "system", "content": "s"}
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    async with client_with(httpx.MockTransport(handler)) as client:
        text = await GroqProvider(client, "gk", "m").complete("s", USER, json_mode=True)
    assert text == '{"a": 1}'


async def test_groq_stream_stops_at_done() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = sse(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            "[DONE]",
            {"choices": [{"delta": {"content": "ignored"}}]},
        )
        return httpx.Response(200, content=body)

    async with client_with(httpx.MockTransport(handler)) as client:
        pieces = [p async for p in GroqProvider(client, "k", "m").stream("s", USER)]
    assert "".join(pieces) == "Hello"


async def test_network_error_becomes_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async with client_with(httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError):
            await GroqProvider(client, "k", "m").complete("s", USER)


class ScriptedProvider:
    """Test double: fails, or yields the given pieces."""

    def __init__(self, name: str, pieces: list[str] | None, fail_after: int | None = None) -> None:
        self.name = name
        self.pieces = pieces
        self.fail_after = fail_after
        self.calls = 0

    async def complete(self, system: str, messages: list[Message], **_: object) -> str:
        self.calls += 1
        if self.pieces is None:
            raise LLMError(f"{self.name} down")
        return "".join(self.pieces)

    async def stream(self, system: str, messages: list[Message], **_: object) -> AsyncIterator[str]:
        self.calls += 1
        if self.pieces is None:
            raise LLMError(f"{self.name} down")
        for i, piece in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise LLMError(f"{self.name} dropped")
            yield piece


async def test_fallback_uses_second_provider_when_first_fails() -> None:
    first, second = ScriptedProvider("a", None), ScriptedProvider("b", ["ok"])
    provider = FallbackProvider([first, second])
    assert await provider.complete("s", USER) == "ok"
    assert "".join([p async for p in provider.stream("s", USER)]) == "ok"


async def test_fallback_does_not_switch_provider_mid_stream() -> None:
    first = ScriptedProvider("a", ["half ", "answer"], fail_after=1)
    second = ScriptedProvider("b", ["other answer"])
    provider = FallbackProvider([first, second])
    received: list[str] = []
    with pytest.raises(LLMError, match="dropped"):
        async for piece in provider.stream("s", USER):
            received.append(piece)
    assert received == ["half "]
    assert second.calls == 0


async def test_fallback_with_no_providers_raises() -> None:
    with pytest.raises(LLMError, match="none configured"):
        await FallbackProvider([]).complete("s", USER)
