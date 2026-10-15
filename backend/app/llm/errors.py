"""Turn a failed provider response into an error message that is useful in the log."""

from __future__ import annotations

import httpx

from app.llm.base import LLMError

MAX_DETAIL = 200


async def http_error(provider: str, response: httpx.Response, api_key: str) -> LLMError:
    """Include the provider's own reason, such as "model not found", with the key removed.

    Both Gemini and Groq return errors as {"error": {"message": ...}}. Their messages
    don't contain the key, but it is scrubbed anyway in case a provider ever echoes it.
    """
    detail = ""
    try:
        await response.aread()
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message.strip():
            detail = ": " + " ".join(message.split())[:MAX_DETAIL]
    except (ValueError, httpx.HTTPError):
        pass
    text = f"{provider} returned HTTP {response.status_code}{detail}"
    if api_key:
        text = text.replace(api_key, "[key]")
    return LLMError(text)
