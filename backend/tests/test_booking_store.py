from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.scheduling.store import BookingStore, NewBooking

START = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)


def booking(start: datetime = START, minutes: int = 40, name: str = "Sam") -> NewBooking:
    return NewBooking("cleaning", start, start + timedelta(minutes=minutes), name, "s@e.co", None)


def test_rooms_fill_up_then_requests_are_refused(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=2)
    first, second = store.create(booking()), store.create(booking())
    assert first is not None and second is not None
    assert {store.get(first)["room"], store.get(second)["room"]} == {1, 2}
    assert store.create(booking(START + timedelta(minutes=20))) is None


def test_back_to_back_appointments_share_a_room(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=1)
    assert store.create(booking()) is not None
    assert store.create(booking(START + timedelta(minutes=40))) is not None


def test_declined_and_cancelled_bookings_free_the_slot(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=1)
    first = store.create(booking())
    assert first is not None
    assert store.transition(first, ("requested",), "declined")
    second = store.create(booking())
    assert second is not None
    assert store.transition(second, ("requested",), "confirmed")
    assert store.transition(second, ("requested", "confirmed"), "cancelled")
    assert store.busy(START, START + timedelta(hours=1)) == []


def test_transitions_only_from_allowed_states(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=1)
    booking_id = store.create(booking())
    assert booking_id is not None
    assert store.transition(booking_id, ("requested",), "confirmed")
    assert not store.transition(booking_id, ("requested",), "declined")
    assert store.get(booking_id)["status"] == "confirmed"


def test_simultaneous_requests_for_the_last_room_only_one_wins(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=1)
    results: list[int | None] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def attempt(i: int) -> None:
        barrier.wait()
        try:
            results.append(store.create(booking(name=f"patient {i}")))
        except BaseException as exc:  # a crashed thread would otherwise go unnoticed
            errors.append(exc)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 8
    assert len([r for r in results if r is not None]) == 1
    assert len(store.list_bookings()) == 1


def test_times_round_trip_in_utc(tmp_path: Path) -> None:
    store = BookingStore(tmp_path / "b.db", rooms=1)
    local = datetime.fromisoformat("2026-10-20T09:00:00-04:00")
    booking_id = store.create(booking(local))
    assert booking_id is not None
    saved = store.get(booking_id)
    assert saved is not None and saved["starts_at"] == "2026-10-20T13:00:00+00:00"
