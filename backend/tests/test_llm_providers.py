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


def capture(seen: dict[str, object], reply: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(handler)


GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
GROQ_OK = {"choices": [{"message": {"content": "ok"}}]}


async def test_gemini_3_uses_low_thinking_and_extra_output_room() -> None:
    seen: dict[str, object] = {}
    async with client_with(capture(seen, GEMINI_OK)) as client:
        await GeminiProvider(client, "k", "gemini-3.8-flash").complete("s", USER, max_tokens=300)
    config = seen["body"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert config["maxOutputTokens"] == 300 + 2048


async def test_older_gemini_models_get_no_thinking_level() -> None:
    seen: dict[str, object] = {}
    async with client_with(capture(seen, GEMINI_OK)) as client:
        await GeminiProvider(client, "k", "gemini-2.0-flash").complete("s", USER, max_tokens=300)
    config = seen["body"]["generationConfig"]
    assert "thinkingConfig" not in config
    assert config["maxOutputTokens"] == 300


async def test_groq_gpt_oss_reasons_briefly_and_hides_reasoning() -> None:
    seen: dict[str, object] = {}
    async with client_with(capture(seen, GROQ_OK)) as client:
        await GroqProvider(client, "k", "openai/gpt-oss-120b").complete("s", USER, max_tokens=300)
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["reasoning_effort"] == "low"
    assert body["include_reasoning"] is False
    assert body["max_completion_tokens"] == 300 + 2048


async def test_groq_other_models_get_plain_requests() -> None:
    seen: dict[str, object] = {}
    async with client_with(capture(seen, GROQ_OK)) as client:
        await GroqProvider(client, "k", "some-model").complete("s", USER, max_tokens=300)
    body = seen["body"]
    assert isinstance(body, dict)
    assert "reasoning_effort" not in body and body["max_completion_tokens"] == 300


async def test_error_includes_the_providers_reason_without_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        message = "models/old-model is not found. Key sk-secret-123 was used."
        return httpx.Response(404, json={"error": {"code": 404, "message": message}})

    async with client_with(httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError) as info:
            await GeminiProvider(client, "sk-secret-123", "old-model").complete("s", USER)
        with pytest.raises(LLMError) as stream_info:
            async for _ in GroqProvider(client, "sk-secret-123", "old-model").stream("s", USER):
                pass
    for error in (info.value, stream_info.value):
        assert "404" in str(error) and "is not found" in str(error)
        assert "sk-secret-123" not in str(error) and "[key]" in str(error)


async def test_error_without_a_json_body_still_reports_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad gateway</html>")

    async with client_with(httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMError, match=r"^Groq returned HTTP 502$"):
            await GroqProvider(client, "k", "m").complete("s", USER)
