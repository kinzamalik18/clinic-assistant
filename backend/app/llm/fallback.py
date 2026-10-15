"""Try providers in order so that one rate-limited or failing provider doesn't take the app down."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence

import httpx

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider

logger = logging.getLogger(__name__)


class FallbackProvider:
    """Try providers in order. A provider that just failed with an overload, rate limit
    or network error is moved to the back of the line for a while, so that during an
    outage every request doesn't wait for it to time out again.
    """

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = list(providers)
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._resting_until: dict[str, float] = {}
        self.name = "+".join(p.name for p in self._providers) or "none"

    def _order(self) -> list[LLMProvider]:
        """Healthy providers first, in configured order, then resting ones as a last resort."""
        now = self._clock()
        healthy = [p for p in self._providers if self._resting_until.get(p.name, 0) <= now]
        resting = [p for p in self._providers if p not in healthy]
        return healthy + resting

    def _failed(self, provider: LLMProvider, exc: LLMError) -> None:
        logger.warning("LLM provider %s failed: %s", provider.name, exc)
        if exc.transient:
            self._resting_until[provider.name] = self._clock() + self._cooldown
            logger.info("Trying other providers first for %.0f seconds", self._cooldown)

    def _succeeded(self, provider: LLMProvider) -> None:
        self._resting_until.pop(provider.name, None)

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
        for provider in self._order():
            try:
                text = await provider.complete(
                    system,
                    messages,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMError as exc:
                self._failed(provider, exc)
                errors.append(str(exc))
                continue
            self._succeeded(provider)
            return text
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
        for provider in self._order():
            started = False
            try:
                async for piece in provider.stream(
                    system, messages, temperature=temperature, max_tokens=max_tokens
                ):
                    started = True
                    yield piece
                if started:
                    self._succeeded(provider)
                    return
                errors.append(f"{provider.name} returned no text")
            except LLMError as exc:
                self._failed(provider, exc)
                if started:
                    raise
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
