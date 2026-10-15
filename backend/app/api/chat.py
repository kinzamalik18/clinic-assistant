"""Patient chat endpoint. Streams the reply as server-sent events."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import enforce
from app.chat.service import ChatPlan, ChatService
from app.llm.base import LLMError, Message
from app.safety import CLINIC_PHONE

logger = logging.getLogger(__name__)
router = APIRouter()

UNAVAILABLE = (
    "Sorry, the assistant isn't available right now. Please call the front desk on "
    f"{CLINIC_PHONE} or use the contact form."
)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


def _event(name: str, data: object) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def _events(service: ChatService, plan: ChatPlan) -> AsyncIterator[str]:
    yield _event("meta", {"kind": plan.kind, "sources": [asdict(s) for s in plan.sources]})
    try:
        async for piece in service.stream(plan):
            yield _event("delta", {"text": piece})
    except LLMError as exc:
        logger.error("Chat generation failed: %s", exc)
        yield _event("error", {"message": UNAVAILABLE})
        return
    yield _event("done", {"kind": plan.kind})


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    enforce(request.app.state.chat_limiter, request)
    service: ChatService = request.app.state.chat_service
    history = [Message(role=t.role, content=t.content) for t in body.history]
    plan = service.plan(body.message, history)
    return StreamingResponse(
        _events(service, plan),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
