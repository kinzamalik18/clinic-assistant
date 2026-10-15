"""Test doubles shared by several test modules."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.base import LLMError, Message


class FakeProvider:
    """Returns scripted text and records what it was asked."""

    name = "fake"

    def __init__(self, reply: str = "", pieces: list[str] | None = None, fail: bool = False):
        self.reply = reply
        self.pieces = pieces
        self.fail = fail
        self.calls: list[tuple[str, list[Message]]] = []

    async def complete(self, system: str, messages: list[Message], **_: object) -> str:
        self.calls.append((system, messages))
        if self.fail:
            raise LLMError("fake failure")
        return self.reply

    async def stream(self, system: str, messages: list[Message], **_: object) -> AsyncIterator[str]:
        self.calls.append((system, messages))
        if self.fail:
            raise LLMError("fake failure")
        for piece in self.pieces if self.pieces is not None else [self.reply]:
            yield piece
