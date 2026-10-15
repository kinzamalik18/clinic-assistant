"""Helpers for API tests."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import SecretStr

from app.config import Settings


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "gemini_api_key": SecretStr(""),
        "groq_api_key": SecretStr(""),
        "staff_token": SecretStr("test-staff-token"),
        "database_path": str(tmp_path / "test.db"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
