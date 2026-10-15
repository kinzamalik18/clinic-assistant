"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI

from app.api import bookings, chat, inbox
from app.chat.service import ChatService
from app.config import Settings, get_settings
from app.inbox.store import MessageStore
from app.inbox.triage import Triager
from app.knowledge.documents import load_chunks
from app.knowledge.retrieval import BM25Retriever
from app.llm.base import LLMProvider
from app.llm.fallback import build_provider
from app.ratelimit import RateLimiter
from app.scheduling.assistant import BookingAssistant
from app.scheduling.slots import SlotRules
from app.scheduling.store import BookingStore
from app.web import add_security_headers, mount_frontend

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    """Build the app. Tests pass their own settings, a fake provider and a fixed clock."""
    settings = settings or get_settings()
    rules = SlotRules(
        tz=ZoneInfo(settings.clinic_timezone),  # fails at startup on a bad time zone name
        rooms=settings.treatment_rooms,
        lead=timedelta(minutes=settings.booking_lead_minutes),
        horizon=timedelta(days=settings.booking_horizon_days),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=5.0)
        ) as client:
            llm = provider or build_provider(settings, client)
            retriever = BM25Retriever(load_chunks(settings.resolve(settings.knowledge_dir)))
            app.state.chat_service = ChatService(
                retriever, llm, settings.retrieval_top_k, settings.retrieval_min_score
            )
            app.state.chat_limiter = RateLimiter(settings.chat_rate_limit_per_minute, 60)
            app.state.triager = Triager(llm, retriever)
            app.state.store = MessageStore(settings.resolve(settings.database_path))
            app.state.contact_limiter = RateLimiter(settings.contact_rate_limit_per_hour, 3600)
            booking_store = BookingStore(
                settings.resolve(settings.database_path), settings.treatment_rooms
            )
            app.state.booking_store = booking_store
            app.state.booking_assistant = BookingAssistant(llm, booking_store, rules, clock)
            app.state.booking_limiter = RateLimiter(settings.booking_rate_limit_per_hour, 3600)
            yield

    app = FastAPI(title="Clinic Assistant", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.slot_rules = rules
    app.state.clock = clock
    app.include_router(chat.router)
    app.include_router(inbox.router)
    app.include_router(bookings.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    add_security_headers(app)
    mount_frontend(app, settings.resolve(settings.static_dir))
    return app


app = create_app()
