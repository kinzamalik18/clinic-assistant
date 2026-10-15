"""Shared request helpers."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.ratelimit import RateLimiter


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    if not limiter.allow(client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment and try again.",
        )
