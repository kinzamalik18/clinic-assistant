"""Serve the built React app and add security headers to every response."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# The app loads only its own scripts, styles and fonts and talks only to its own API.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)

SECURITY_HEADERS = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("cache-control", "no-store")
        return response


def mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():
        logger.info("No built frontend at %s; serving the API only", dist)
        return

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    def page() -> FileResponse:
        return FileResponse(index, headers={"cache-control": "no-cache"})

    # The two pages of the single-page app. Other paths fall through to a 404.
    app.add_api_route("/", page, include_in_schema=False)
    app.add_api_route("/staff", page, include_in_schema=False)

    favicon = dist / "favicon.svg"
    if favicon.is_file():
        app.add_api_route("/favicon.svg", lambda: FileResponse(favicon), include_in_schema=False)
