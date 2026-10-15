"""SQLite storage for appointment requests.

A requested appointment holds its slot until staff confirm or decline it. Choosing a
room and inserting the row happen inside one write-locked transaction, so two
patients picking the same time at once can't both get it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.scheduling.slots import Booked, free_room

# requested -> confirmed | declined; requested or confirmed -> cancelled
ACTIVE = ("requested", "confirmed")
STATUSES = ("requested", "confirmed", "declined", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    service TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    room INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'requested',
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bookings_time ON bookings (starts_at, ends_at);
"""


def _utc(value: datetime) -> str:
    """Store times as UTC ISO strings, which sort and compare correctly as text."""
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _now() -> str:
    return _utc(datetime.now(timezone.utc))


@dataclass(frozen=True)
class NewBooking:
    service: str
    start: datetime
    end: datetime
    name: str
    email: str
    phone: str | None


class BookingStore:
    def __init__(self, path: Path, rooms: int) -> None:
        if rooms < 1:
            raise ValueError("There must be at least one treatment room")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._rooms = rooms
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # isolation_level=None lets each method control its own transaction.
        db = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _active_between(
        self, db: sqlite3.Connection, start: datetime, end: datetime
    ) -> list[Booked]:
        rows = db.execute(
            "SELECT room, starts_at, ends_at FROM bookings "
            "WHERE status IN (SELECT value FROM json_each(?)) AND starts_at < ? AND ends_at > ?",
            (json.dumps(ACTIVE), _utc(end), _utc(start)),
        ).fetchall()
        return [
            Booked(
                room=r["room"],
                start=datetime.fromisoformat(r["starts_at"]),
                end=datetime.fromisoformat(r["ends_at"]),
            )
            for r in rows
        ]

    def busy(self, start: datetime, end: datetime) -> list[Booked]:
        """Active appointments that overlap the given window."""
        with self._connect() as db:
            return self._active_between(db, start, end)

    def create(self, booking: NewBooking) -> int | None:
        """Hold the slot and return the new id, or None if every room is taken."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")  # take the write lock before checking
            try:
                busy = self._active_between(db, booking.start, booking.end)
                room = free_room(booking.start, booking.end, busy, self._rooms)
                if room is None:
                    db.execute("ROLLBACK")
                    return None
                cursor = db.execute(
                    "INSERT INTO bookings (created_at, service, starts_at, ends_at, room, "
                    "name, email, phone) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _now(),
                        booking.service,
                        _utc(booking.start),
                        _utc(booking.end),
                        room,
                        booking.name,
                        booking.email,
                        booking.phone,
                    ),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            if cursor.lastrowid is None:
                raise RuntimeError("Insert did not return a row id")
            return cursor.lastrowid

    def get(self, booking_id: int) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return dict(row) if row else None

    def list_bookings(self, status: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
        query = "SELECT * FROM bookings"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY starts_at LIMIT ?"
        with self._connect() as db:
            return [dict(r) for r in db.execute(query, (*params, limit)).fetchall()]

    def transition(self, booking_id: int, allowed: tuple[str, ...], new_status: str) -> bool:
        """Change status only from an allowed state. False if the booking was in another state."""
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE bookings SET status = ?, reviewed_at = ? "
                "WHERE id = ? AND status IN (SELECT value FROM json_each(?))",
                (new_status, _now(), booking_id, json.dumps(allowed)),
            )
            return cursor.rowcount == 1
