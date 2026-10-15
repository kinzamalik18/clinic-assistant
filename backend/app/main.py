"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api import chat, inbox
from app.chat.service import ChatService
from app.config import Settings, get_settings
from app.inbox.store import MessageStore
from app.inbox.triage import Triager
from app.knowledge.documents import load_chunks
from app.knowledge.retrieval import BM25Retriever
from app.llm.base import LLMProvider
from app.llm.fallback import build_provider
from app.ratelimit import RateLimiter
from app.web import add_security_headers, mount_frontend

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings and a fake provider."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            llm = provider or build_provider(settings, client)
            retriever = BM25Retriever(load_chunks(settings.resolve(settings.knowledge_dir)))
            app.state.chat_service = ChatService(
                retriever, llm, settings.retrieval_top_k, settings.retrieval_min_score
            )
            app.state.chat_limiter = RateLimiter(settings.chat_rate_limit_per_minute, 60)
            app.state.triager = Triager(llm, retriever)
            app.state.store = MessageStore(settings.resolve(settings.database_path))
            app.state.contact_limiter = RateLimiter(settings.contact_rate_limit_per_hour, 3600)
            yield

    app = FastAPI(title="Clinic Assistant", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(chat.router)
    app.include_router(inbox.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    add_security_headers(app)
    mount_frontend(app, settings.resolve(settings.static_dir))
    return app


app = create_app()
