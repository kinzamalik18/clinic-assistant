"""SQLite storage for contact messages and their review state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.inbox.triage import Triage

# A message moves through these states:
#   new -> needs_review -> sent | rejected
#   new -> triage_failed -> (retry) new, or staff handle it by hand -> sent | rejected
REVIEWABLE = ("needs_review", "triage_failed")
STATUSES = ("new", "needs_review", "triage_failed", "sent", "rejected")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    priority TEXT,
    summary TEXT,
    draft_reply TEXT,
    final_reply TEXT,
    edited INTEGER,
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages (status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MessageStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:  # commits on success, rolls back on error
                yield db
        finally:
            db.close()

    def create(self, name: str, email: str, phone: str | None, subject: str, body: str) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO messages (created_at, name, email, phone, subject, body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), name, email, phone, subject, body),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Insert did not return a row id")
            return cursor.lastrowid

    def get(self, message_id: int) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return dict(row) if row else None

    def list_messages(self, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        query = (
            "SELECT id, created_at, name, subject, status, category, priority, summary "
            "FROM messages"
        )
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        # Urgent first, then high, then everything else, newest first within a group.
        query += (
            " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,"
            " id DESC LIMIT ?"
        )
        with self._connect() as db:
            rows = db.execute(query, (*params, limit)).fetchall()
        return [dict(r) for r in rows]

    def save_triage(self, message_id: int, triage: Triage) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE messages SET status = 'needs_review', category = ?, priority = ?, "
                "summary = ?, draft_reply = ? WHERE id = ? AND status = 'new'",
                (
                    triage.category.value,
                    triage.priority.value,
                    triage.summary,
                    triage.draft_reply,
                    message_id,
                ),
            )
            return cursor.rowcount == 1

    def mark_failed(self, message_id: int) -> bool:
        return self._transition(message_id, ("new",), "triage_failed")

    def reset_for_retry(self, message_id: int) -> bool:
        return self._transition(message_id, ("triage_failed",), "new")

    def approve(self, message_id: int, reply: str) -> bool:
        """Mark a message as answered. Returns False if it was not awaiting review.

        The status check is part of the UPDATE, so two staff members approving the same
        message at once can't both succeed.
        """
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE messages SET status = 'sent', final_reply = ?, reviewed_at = ?, "
                "edited = CASE WHEN draft_reply IS NULL THEN 1 "
                "WHEN TRIM(draft_reply) = TRIM(?) THEN 0 ELSE 1 END "
                "WHERE id = ? AND status IN (SELECT value FROM json_each(?))",
                (reply, _now(), reply, message_id, json.dumps(REVIEWABLE)),
            )
            return cursor.rowcount == 1

    def reject(self, message_id: int) -> bool:
        return self._transition(message_id, REVIEWABLE, "rejected")

    def _transition(self, message_id: int, allowed: tuple[str, ...], new_status: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE messages SET status = ?, reviewed_at = ? "
                "WHERE id = ? AND status IN (SELECT value FROM json_each(?))",
                (new_status, _now(), message_id, json.dumps(allowed)),
            )
            return cursor.rowcount == 1

    def stats(self) -> dict[str, Any]:
        with self._connect() as db:
            by_status = dict(
                db.execute("SELECT status, COUNT(*) FROM messages GROUP BY status").fetchall()
            )
            by_category = dict(
                db.execute(
                    "SELECT category, COUNT(*) FROM messages WHERE category IS NOT NULL "
                    "GROUP BY category"
                ).fetchall()
            )
            sent, edited = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(edited), 0) FROM messages WHERE status = 'sent'"
            ).fetchone()
        return {
            "by_status": {s: by_status.get(s, 0) for s in STATUSES},
            "by_category": by_category,
            "sent": sent,
            "sent_without_edits": sent - edited,
        }
