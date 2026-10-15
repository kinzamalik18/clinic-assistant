from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.scheduling.clinic import SERVICES
from app.scheduling.slots import Booked, SlotRules, find_slots, free_room, is_bookable

TZ = ZoneInfo("America/New_York")
RULES = SlotRules(tz=TZ, rooms=1, lead=timedelta(hours=2), horizon=timedelta(days=14))
CLEANING = SERVICES["cleaning"]
WHITENING = SERVICES["whitening"]

# 2026-10-19 is a Monday.
MON = date(2026, 10, 19)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def test_offers_one_slot_per_day_earliest_first() -> None:
    now = at(MON, 6)
    slots = find_slots(CLEANING, MON, MON + timedelta(days=6), now, [], RULES)
    assert slots == [at(MON, 8), at(MON + timedelta(days=1), 8), at(MON + timedelta(days=2), 8)]


def test_respects_lead_time() -> None:
    now = at(MON, 10, 5)
    slots = find_slots(CLEANING, MON, MON, now, [], RULES, limit=1)
    assert slots == [at(MON, 12, 15)]


def test_appointment_must_end_by_closing_time() -> None:
    friday = MON + timedelta(days=4)
    now = at(friday, 6)
    # Whitening takes 90 minutes and Friday closes at 4 pm.
    assert is_bookable(WHITENING, at(friday, 14, 30), now, RULES)
    assert not is_bookable(WHITENING, at(friday, 14, 45), now, RULES)


def test_saturday_only_for_checkups_and_cleanings() -> None:
    saturday = MON + timedelta(days=5)
    now = at(MON, 6)
    assert find_slots(CLEANING, saturday, saturday, now, [], RULES)
    assert find_slots(WHITENING, saturday, saturday, now, [], RULES) == []


def test_sunday_is_closed() -> None:
    sunday = MON + timedelta(days=6)
    assert find_slots(CLEANING, sunday, sunday, at(MON, 6), [], RULES) == []


def test_part_of_day_and_weekday_filters() -> None:
    now = at(MON, 6)
    slots = find_slots(
        CLEANING, MON, MON + timedelta(days=6), now, [], RULES, part="afternoon", weekdays={2}
    )
    wednesday = MON + timedelta(days=2)
    assert slots == [at(wednesday, 12), at(wednesday, 13), at(wednesday, 14)]


def test_busy_rooms_block_overlapping_times() -> None:
    now = at(MON, 6)
    booked = [Booked(room=1, start=at(MON, 8), end=at(MON, 9, 30))]
    slots = find_slots(CLEANING, MON, MON, now, booked, RULES, limit=1)
    assert slots == [at(MON, 9, 30)]
    two_rooms = SlotRules(tz=TZ, rooms=2, lead=RULES.lead, horizon=RULES.horizon)
    assert find_slots(CLEANING, MON, MON, now, booked, two_rooms, limit=1) == [at(MON, 8)]


def test_free_room_treats_back_to_back_as_free() -> None:
    booked = [Booked(room=1, start=at(MON, 8), end=at(MON, 8, 40))]
    assert free_room(at(MON, 8, 40), at(MON, 9, 20), booked, rooms=1) == 1
    assert free_room(at(MON, 8, 30), at(MON, 9, 10), booked, rooms=1) is None


def test_never_looks_past_the_horizon() -> None:
    now = at(MON, 6)
    far = MON + timedelta(days=30)
    assert find_slots(CLEANING, far, far, now, [], RULES) == []


def test_is_bookable_rejects_odd_times_and_wrong_days() -> None:
    now = at(MON, 6)
    tuesday = MON + timedelta(days=1)
    assert is_bookable(CLEANING, at(tuesday, 9, 15), now, RULES)
    assert not is_bookable(CLEANING, at(tuesday, 9, 10), now, RULES)  # not on the 15-minute grid
    assert not is_bookable(CLEANING, at(tuesday, 17, 30), now, RULES)  # would end after 6 pm
    assert not is_bookable(WHITENING, at(MON + timedelta(days=5), 9), now, RULES)  # Saturday
    assert not is_bookable(CLEANING, at(MON, 7), now, RULES)  # before opening, inside lead time


def test_daylight_saving_change_keeps_clinic_hours() -> None:
    # US clocks go back on 2026-11-01. The Monday after still opens at 8 am local time.
    monday = date(2026, 11, 2)
    now = at(date(2026, 10, 31), 12)
    slots = find_slots(CLEANING, monday, monday, now, [], RULES, limit=1)
    assert slots == [at(monday, 8)]
    assert slots[0].utcoffset() == timedelta(hours=-5)
