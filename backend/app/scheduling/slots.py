"""Find open appointment times. Plain date arithmetic, no model involved."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.scheduling.clinic import OPENING_HOURS, SATURDAY, SLOT_STEP_MINUTES, Service

PartOfDay = Literal["any", "morning", "afternoon"]
NOON = 12 * 60
MIN_GAP_SAME_DAY = timedelta(hours=1)


@dataclass(frozen=True)
class Booked:
    """An existing appointment that occupies a treatment room."""

    room: int
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SlotRules:
    tz: ZoneInfo
    rooms: int
    lead: timedelta
    horizon: timedelta


def overlaps(start: datetime, end: datetime, other: Booked) -> bool:
    return start < other.end and other.start < end


def free_room(start: datetime, end: datetime, booked: Iterable[Booked], rooms: int) -> int | None:
    """Lowest-numbered room with no overlapping appointment, or None if all are taken."""
    taken = {b.room for b in booked if overlaps(start, end, b)}
    return next((r for r in range(1, rooms + 1) if r not in taken), None)


def _day_starts(service: Service, day: date, tz: ZoneInfo) -> Iterator[datetime]:
    hours = OPENING_HOURS.get(day.weekday())
    if hours is None or (day.weekday() == SATURDAY and not service.saturday):
        return
    opens, closes = hours
    start = datetime.combine(day, opens, tzinfo=tz)
    last = datetime.combine(day, closes, tzinfo=tz) - timedelta(minutes=service.minutes)
    while start <= last:
        yield start
        start += timedelta(minutes=SLOT_STEP_MINUTES)


def _matches(start: datetime, part: PartOfDay) -> bool:
    minute = start.hour * 60 + start.minute
    if part == "morning":
        return minute < NOON
    if part == "afternoon":
        return minute >= NOON
    return True


def is_bookable(service: Service, start: datetime, now: datetime, rules: SlotRules) -> bool:
    """Check that `start` is a real slot time for this service, ignoring other bookings."""
    local = start.astimezone(rules.tz)
    if not now + rules.lead <= start <= now + rules.horizon:
        return False
    return any(s == local for s in _day_starts(service, local.date(), rules.tz))


def find_slots(
    service: Service,
    first_day: date,
    last_day: date,
    now: datetime,
    booked: list[Booked],
    rules: SlotRules,
    part: PartOfDay = "any",
    weekdays: set[int] | None = None,
    limit: int = 3,
) -> list[datetime]:
    """Return up to `limit` open start times, at most one per day, earliest first.

    Offering different days gives the patient real choice; if there are fewer days
    than `limit`, times at least an hour apart from the same days fill the list.
    """
    earliest = now + rules.lead
    latest_day = min(last_day, (now + rules.horizon).astimezone(rules.tz).date())
    per_day: list[list[datetime]] = []
    day = max(first_day, earliest.astimezone(rules.tz).date())
    while day <= latest_day:
        if weekdays is None or day.weekday() in weekdays:
            open_times = [
                s
                for s in _day_starts(service, day, rules.tz)
                if s >= earliest
                and _matches(s, part)
                and free_room(s, s + timedelta(minutes=service.minutes), booked, rules.rooms)
                is not None
            ]
            if open_times:
                per_day.append(open_times)
        day += timedelta(days=1)

    picked = [times[0] for times in per_day][:limit]
    for times in per_day:
        for extra in times[1:]:
            if len(picked) >= limit:
                break
            # Extra times on a day already offered are spread out, so the choices
            # are not 12:00, 12:15 and 12:30.
            if all(abs(extra - p) >= MIN_GAP_SAME_DAY for p in picked):
                picked.append(extra)
    return sorted(picked)[:limit]
