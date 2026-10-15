"""Shared request helpers: rate limiting, staff authentication and form field rules."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import HTTPException, Request, status
from pydantic import Field, StringConstraints

from app.ratelimit import RateLimiter

MIN_STAFF_TOKEN_LENGTH = 16

Text = Annotated[str, StringConstraints(strip_whitespace=True)]
Name = Annotated[Text, StringConstraints(min_length=1, max_length=100)]
Email = Annotated[Text, StringConstraints(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Phone = Annotated[Text, StringConstraints(max_length=30)]
# Hidden form field. People never fill it in; simple spam bots usually do.
Honeypot = Annotated[str, Field(max_length=200)]


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    if not limiter.allow(client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment and try again.",
        )


def require_staff(request: Request) -> None:
    expected = request.app.state.settings.staff_token.get_secret_value()
    if len(expected) < MIN_STAFF_TOKEN_LENGTH:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Staff access is disabled. Set STAFF_TOKEN (16+ characters) on the server.",
        )
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid staff token",
            headers={"www-authenticate": "Bearer"},
        )
