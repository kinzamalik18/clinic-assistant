"""Provider-neutral types for talking to a chat model."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


class LLMError(Exception):
    """A model call failed. The message is safe to log; it never contains API keys.

    `transient` marks failures that usually clear up by themselves: overload, rate
    limits and network problems. A wrong key or model name is not transient.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Return the full response text. With json_mode the model is asked for a JSON object."""
        ...

    def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Yield the response text in pieces as the model produces it."""
        ...
