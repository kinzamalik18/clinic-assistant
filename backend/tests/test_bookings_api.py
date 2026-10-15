from __future__ import annotations

import json
import typing
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.bookings import ServiceKey
from app.main import create_app
from app.scheduling.clinic import SERVICES
from tests.fakes import FakeProvider
from tests.helpers import make_settings, parse_sse

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=TZ)  # a Wednesday
AUTH = {"authorization": "Bearer test-staff-token"}
INTENT = json.dumps(
    {
        "wants_appointment": True,
        "service": "cleaning",
        "when": "next_week",
        "part_of_day": "morning",
    }
)
FORM = {
    "service": "cleaning",
    "start": "2026-10-19T08:00:00-04:00",
    "name": "Priya Nair",
    "email": "priya@example.com",
}

ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(tmp_path: Path) -> ClientFactory:
    def factory(reply: str = INTENT, **overrides: object) -> TestClient:
        settings = make_settings(tmp_path, **overrides)
        return TestClient(
            create_app(settings, provider=FakeProvider(reply=reply), clock=lambda: NOW)
        )

    return factory


def test_service_keys_in_the_api_match_the_clinic_services() -> None:
    assert set(typing.get_args(ServiceKey)) == set(SERVICES)


def test_chat_offers_open_times_for_a_booking_request(make_client: ClientFactory) -> None:
    with make_client() as c:
        response = c.post("/api/chat", json={"message": "Can I book a cleaning next week?"})
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["meta", "delta", "slots", "done"]
    slots = events[2][1]
    assert slots["service"] == "cleaning"
    assert isinstance(slots["slots"], list)
    assert slots["slots"][0] == {
        "start": "2026-10-19T08:00:00-04:00",
        "label": "Mon 19 Oct, 8:00 am",
    }


def test_emergency_is_never_offered_appointments(make_client: ClientFactory) -> None:
    with make_client() as c:
        body = {"message": "Can I book in? My face is swelling up towards my eye", "mode": "book"}
        events = parse_sse(c.post("/api/chat", json=body).text)
    assert events[0][1]["kind"] == "emergency"
    assert "slots" not in [name for name, _ in events]


def test_question_that_mentions_appointments_gets_a_normal_answer(
    make_client: ClientFactory,
) -> None:
    not_booking = json.dumps({"wants_appointment": False, "service": "unknown"})
    with make_client(reply=not_booking) as c:
        message = {"message": "What is the fee if I miss an appointment?"}
        events = parse_sse(c.post("/api/chat", json=message).text)
    assert events[0][1]["kind"] == "answer"


def test_booking_holds_the_slot_and_staff_confirm_it(make_client: ClientFactory) -> None:
    with make_client(treatment_rooms=1) as c:
        created = c.post("/api/bookings", json=FORM)
        assert created.status_code == 201
        assert created.json() == {
            "status": "requested",
            "when": "Mon 19 Oct, 8:00 am",
            "service_label": "Cleaning",
        }

        # The held time is no longer offered in the chat.
        events = parse_sse(c.post("/api/chat", json={"message": "book a cleaning"}).text)
        assert events[2][1]["slots"][0]["label"] != "Mon 19 Oct, 8:00 am"

        listed = c.get("/api/staff/bookings", headers=AUTH).json()
        assert len(listed) == 1 and listed[0]["when"] == "Mon 19 Oct, 8:00 am"
        booking_id = listed[0]["id"]
        assert (
            c.post(f"/api/staff/bookings/{booking_id}/confirm", headers=AUTH).json()["status"]
            == "confirmed"
        )
        assert c.post(f"/api/staff/bookings/{booking_id}/decline", headers=AUTH).status_code == 409
        cancelled = c.post(f"/api/staff/bookings/{booking_id}/cancel", headers=AUTH)
        assert cancelled.json()["status"] == "cancelled"
        assert c.post("/api/staff/bookings/999/confirm", headers=AUTH).status_code == 404


def test_a_taken_time_cannot_be_booked_twice(make_client: ClientFactory) -> None:
    with make_client(treatment_rooms=1) as c:
        assert c.post("/api/bookings", json=FORM).status_code == 201
        second = c.post("/api/bookings", json={**FORM, "name": "Someone Else"})
    assert second.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"start": "2026-10-19T08:10:00-04:00"},  # not a slot time
        {"start": "2026-10-18T10:00:00-04:00"},  # Sunday
        {"start": "2026-10-14T09:30:00-04:00"},  # inside the two-hour lead time
        {"start": "2026-11-20T09:00:00-05:00"},  # beyond two weeks
        {"service": "whitening", "start": "2026-10-24T09:00:00-04:00"},  # Saturday
    ],
)
def test_times_that_were_never_offered_are_refused(
    make_client: ClientFactory, change: dict[str, str]
) -> None:
    with make_client() as c:
        assert c.post("/api/bookings", json={**FORM, **change}).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"start": "2026-10-19T08:00:00"},  # no time zone
        {"service": "root_canal"},
        {"email": "nope"},
        {"name": " "},
    ],
)
def test_booking_form_validation(make_client: ClientFactory, change: dict[str, str]) -> None:
    with make_client() as c:
        assert c.post("/api/bookings", json={**FORM, **change}).status_code == 422


def test_honeypot_bookings_are_not_stored(make_client: ClientFactory) -> None:
    with make_client() as c:
        response = c.post("/api/bookings", json={**FORM, "website": "spam"})
        assert response.status_code == 201
        assert c.get("/api/staff/bookings", headers=AUTH).json() == []


def test_booking_rate_limit(make_client: ClientFactory) -> None:
    times = ["08:00", "09:00", "10:00"]
    with make_client(booking_rate_limit_per_hour=2) as c:
        codes = [
            c.post("/api/bookings", json={**FORM, "start": f"2026-10-19T{t}:00-04:00"}).status_code
            for t in times
        ]
    assert codes == [201, 201, 429]


def test_staff_booking_endpoints_need_the_token(make_client: ClientFactory) -> None:
    with make_client() as c:
        assert c.get("/api/staff/bookings").status_code == 401
        assert c.post("/api/staff/bookings/1/confirm").status_code == 401
