"""Helpers for reading server-sent event streams from model APIs."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


async def iter_sse_json(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Yield the JSON payload of each `data:` line. Stops at the OpenAI-style `[DONE]` marker."""
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        if payload == "[DONE]":
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            yield data
