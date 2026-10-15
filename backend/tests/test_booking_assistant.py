from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.llm.base import LLMError
from app.scheduling.assistant import (
    BookingAssistant,
    _describe,
    format_slot,
    looks_like_booking,
)
from app.scheduling.intent import BookingIntent
from app.scheduling.slots import SlotRules
from app.scheduling.store import BookingStore, NewBooking
from tests.fakes import FakeProvider

pytestmark = pytest.mark.anyio

TZ = ZoneInfo("America/New_York")
RULES = SlotRules(tz=TZ, rooms=1, lead=timedelta(hours=2), horizon=timedelta(days=14))
# Wednesday 2026-10-14, 9 am clinic time.
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=TZ)


def intent(**fields: object) -> str:
    data: dict[str, object] = {"wants_appointment": True, "service": "cleaning", "when": "soonest"}
    data.update(fields)
    return json.dumps(data)


def assistant(tmp_path: Path, reply: str, rooms: int = 1) -> tuple[BookingAssistant, BookingStore]:
    store = BookingStore(tmp_path / "b.db", rooms=rooms)
    return BookingAssistant(FakeProvider(reply=reply), store, RULES, lambda: NOW), store


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Can I book a cleaning next week?", True),
        ("Do you have any openings on Saturday?", True),
        ("When can I come in for a check-up?", True),
        ("A check-up on Saturday morning please", True),
        ("I'm new and want to register", True),
        ("How much is a cleaning?", False),
        ("Do you take Delta Dental?", False),
    ],
)
def test_booking_hint(text: str, expected: bool) -> None:
    assert looks_like_booking(text) is expected


def test_format_slot() -> None:
    assert format_slot(datetime(2026, 10, 20, 9, 5, tzinfo=TZ)) == "Tue 20 Oct, 9:05 am"
    assert format_slot(datetime(2026, 10, 20, 12, 0, tzinfo=TZ)) == "Tue 20 Oct, 12:00 pm"


@pytest.mark.parametrize(
    ("fields", "window"),
    [
        ({"when": "soonest"}, (date(2026, 10, 14), date(2026, 10, 28))),
        ({"when": "this_week"}, (date(2026, 10, 14), date(2026, 10, 18))),
        ({"when": "next_week"}, (date(2026, 10, 19), date(2026, 10, 25))),
        ({"when": "on_date", "date_from": "2026-10-22"}, (date(2026, 10, 22), date(2026, 10, 22))),
        (
            {"when": "between_dates", "date_from": "2026-10-30", "date_to": "2026-10-20"},
            (date(2026, 10, 20), date(2026, 10, 28)),
        ),
        ({"when": "on_date", "date_from": "2026-01-01"}, (date(2026, 10, 14), date(2026, 1, 1))),
        ({"when": "on_date"}, (date(2026, 10, 14), date(2026, 10, 28))),
    ],
)
def test_window_is_resolved_in_code_and_clamped(
    fields: dict[str, object], window: tuple[date, date]
) -> None:
    parsed = BookingIntent.model_validate(json.loads(intent(**fields)))
    assert parsed.window(date(2026, 10, 14), 14) == window


async def test_offers_open_times_with_the_patients_preferences(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, intent(when="next_week", part_of_day="morning"))
    proposal = await helper.propose("Cleaning next week, mornings please", [])
    assert proposal is not None
    assert proposal.service == "cleaning"
    assert [s.label for s in proposal.slots] == [
        "Mon 19 Oct, 8:00 am",
        "Tue 20 Oct, 8:00 am",
        "Wed 21 Oct, 8:00 am",
    ]
    assert proposal.text == (
        "Here are open times for a cleaning in the morning next week. "
        "Pick one and we'll hold it for you."
    )


@pytest.mark.parametrize(
    ("fields", "described"),
    [
        ({"part_of_day": "morning", "when": "next_week"}, "in the morning next week"),
        ({"weekdays": ["tuesday"], "part_of_day": "morning"}, "on Tuesday morning"),
        ({"weekdays": ["monday", "friday"], "when": "this_week"}, "on Monday or Friday this week"),
        (
            {
                "weekdays": ["thursday"],
                "part_of_day": "afternoon",
                "when": "on_date",
                "date_from": "2026-10-15",
            },
            "on Thursday 15 October in the afternoon",
        ),
        ({}, ""),
    ],
)
def test_describe_names_each_preference_once(fields: dict[str, object], described: str) -> None:
    parsed = BookingIntent.model_validate(json.loads(intent(**fields)))
    assert _describe(parsed) == described


async def test_held_slots_are_not_offered_again(tmp_path: Path) -> None:
    helper, store = assistant(tmp_path, intent(when="on_date", date_from="2026-10-19"))
    monday_8 = datetime(2026, 10, 19, 8, 0, tzinfo=TZ)
    store.create(
        NewBooking("cleaning", monday_8, monday_8 + timedelta(minutes=40), "A", "a@b.co", None)
    )
    proposal = await helper.propose("Cleaning on Monday 19th", [])
    assert proposal is not None
    assert proposal.slots[0].label == "Mon 19 Oct, 8:45 am"


async def test_not_a_booking_returns_none(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, intent(wants_appointment=False))
    assert await helper.propose("What's the fee if I miss an appointment?", []) is None


async def test_booking_button_forces_a_booking_flow(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, intent(wants_appointment=False, service="unknown"))
    proposal = await helper.propose("Book an appointment", [], forced=True)
    assert proposal is not None
    assert proposal.slots == []
    assert {c["key"] for c in proposal.choices} >= {"cleaning", "whitening"}


async def test_unknown_service_asks_which_one(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, intent(service="root_canal"))
    proposal = await helper.propose("I need a root canal appointment", [])
    assert proposal is not None and proposal.choices and "(555) 010-2400" in proposal.text


async def test_no_match_falls_back_to_next_available(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, intent(service="whitening", weekdays=["saturday"]))
    proposal = await helper.propose("Whitening on a Saturday", [])
    assert proposal is not None
    assert proposal.text.startswith("There are no openings for an in-clinic whitening on Saturday.")
    assert len(proposal.slots) == 3


async def test_invalid_model_output_raises(tmp_path: Path) -> None:
    helper, _ = assistant(tmp_path, "not json")
    with pytest.raises(LLMError):
        await helper.propose("book a cleaning", [])


@pytest.mark.parametrize(
    "payload",
    [
        {"wants_appointment": False, "service": None},
        {"wants_appointment": False, "service": "unknown", "when": None, "weekdays": None},
        {"wants_appointment": True, "service": "unknown", "date_from": "", "part_of_day": ""},
        {"wants_appointment": False},
    ],
)
def test_blank_fields_mean_not_specified(payload: dict[str, object]) -> None:
    parsed = BookingIntent.model_validate(payload)
    assert parsed.service == "unknown" and parsed.when == "soonest" and parsed.weekdays == []


def test_unexpected_values_fall_back_to_defaults() -> None:
    parsed = BookingIntent.model_validate(
        {
            "wants_appointment": True,
            "service": " Cleaning ",
            "when": "tomorrow",
            "weekdays": ["Monday", "someday", 3],
            "part_of_day": "evening",
        }
    )
    assert parsed.service == "cleaning"
    assert parsed.when == "soonest"
    assert parsed.weekdays == ["monday"]
    assert parsed.part_of_day == "any"
