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
from app.safety import CLINIC_PHONE, check_message
from app.scheduling.assistant import BookingAssistant, looks_like_booking

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
    # "book" is sent when the patient presses a booking button in the widget.
    mode: Literal["chat", "book"] = "chat"


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


async def _respond(
    chat: ChatService,
    booking: BookingAssistant,
    message: str,
    history: list[Message],
    mode: str,
) -> AsyncIterator[str]:
    # Safety rules always come first: someone describing an emergency is never
    # offered appointment times.
    safe = check_message(message) is None
    if safe and (mode == "book" or looks_like_booking(message)):
        try:
            proposal = await booking.propose(message, history, forced=mode == "book")
        except LLMError as exc:
            # Reading the request failed. A normal answer is better than an error,
            # and the booking button stays available.
            logger.warning("Booking request could not be read, answering normally: %s", exc)
            proposal = None
        if proposal is not None:
            yield _event("meta", {"kind": "booking", "sources": []})
            yield _event("delta", {"text": proposal.text})
            yield _event(
                "slots",
                {
                    "service": proposal.service,
                    "service_label": proposal.service_label,
                    "slots": [asdict(s) for s in proposal.slots],
                    "choices": proposal.choices,
                },
            )
            yield _event("done", {"kind": "booking"})
            return

    async for event in _events(chat, chat.plan(message, history)):
        yield event


@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    enforce(request.app.state.chat_limiter, request)
    history = [Message(role=t.role, content=t.content) for t in body.history]
    return StreamingResponse(
        _respond(
            request.app.state.chat_service,
            request.app.state.booking_assistant,
            body.message,
            history,
            body.mode,
        ),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
