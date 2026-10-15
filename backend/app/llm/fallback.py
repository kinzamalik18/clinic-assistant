"""Try providers in order so that one rate-limited or failing provider doesn't take the app down."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

import httpx

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider

logger = logging.getLogger(__name__)


class FallbackProvider:
    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        self._providers = list(providers)
        self.name = "+".join(p.name for p in self._providers) or "none"

    async def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.complete(
                    system,
                    messages,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMError as exc:
                logger.warning("LLM provider %s failed: %s", provider.name, exc)
                errors.append(str(exc))
        raise LLMError("All LLM providers failed: " + "; ".join(errors or ["none configured"]))

    async def stream(
        self,
        system: str,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Fall back only if a provider fails before sending any text.

        Switching providers halfway through an answer would give the user two
        half-answers glued together, so a mid-stream failure is raised instead.
        """
        errors: list[str] = []
        for provider in self._providers:
            started = False
            try:
                async for piece in provider.stream(
                    system, messages, temperature=temperature, max_tokens=max_tokens
                ):
                    started = True
                    yield piece
                if started:
                    return
                errors.append(f"{provider.name} returned no text")
            except LLMError as exc:
                if started:
                    raise
                logger.warning("LLM provider %s failed: %s", provider.name, exc)
                errors.append(str(exc))
        raise LLMError("All LLM providers failed: " + "; ".join(errors or ["none configured"]))


def build_provider(settings: Settings, client: httpx.AsyncClient) -> FallbackProvider:
    """Create the configured providers in order, skipping any without an API key."""
    providers: list[LLMProvider] = []
    for name in settings.provider_order:
        if name == "gemini" and settings.gemini_api_key.get_secret_value():
            providers.append(
                GeminiProvider(
                    client, settings.gemini_api_key.get_secret_value(), settings.gemini_model
                )
            )
        elif name == "groq" and settings.groq_api_key.get_secret_value():
            providers.append(
                GroqProvider(client, settings.groq_api_key.get_secret_value(), settings.groq_model)
            )
    if not providers:
        logger.warning("No LLM provider has an API key; chat and inbox triage are disabled")
    return FallbackProvider(providers)
