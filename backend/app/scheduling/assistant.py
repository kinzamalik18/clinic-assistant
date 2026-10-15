"""Answer a booking request in the chat with real open times."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.llm.base import LLMProvider, Message
from app.safety import CLINIC_PHONE
from app.scheduling.clinic import SERVICES, Service
from app.scheduling.intent import BookingIntent, extract_intent
from app.scheduling.slots import SlotRules, find_slots
from app.scheduling.store import BookingStore

# Cheap first check so ordinary questions don't cost an extra model call. Booking words,
# a named day or time of day, or registering as a new patient all count as hints.
_BOOKING_HINT = re.compile(
    r"\b(book|booking|appointment|appt|schedule|available|availability|slots?|openings?"
    r"|reserve|come in|fit me in|see (?:a|the) (?:dentist|hygienist)"
    r"|today|tomorrow|tonight|next week|this week|mornings?|afternoons?"
    r"|(?:mon|tues|wednes|thurs|fri|satur|sun)days?"
    r"|register|new patient|first (?:visit|exam|appointment))",
    re.IGNORECASE,
)


def looks_like_booking(text: str) -> bool:
    return bool(_BOOKING_HINT.search(text))


def format_slot(start: datetime) -> str:
    """'Tue 21 Oct, 9:00 am'. Built by hand because %-d and %-I don't exist on Windows."""
    hour = start.hour % 12 or 12
    suffix = "am" if start.hour < 12 else "pm"
    return f"{start:%a} {start.day} {start:%b}, {hour}:{start.minute:02d} {suffix}"


@dataclass(frozen=True)
class SlotOffer:
    start: str  # ISO 8601 with the clinic's UTC offset
    label: str


@dataclass
class Proposal:
    text: str
    service: str | None = None
    service_label: str | None = None
    slots: list[SlotOffer] = field(default_factory=list)
    choices: list[dict[str, str]] = field(default_factory=list)


def _with_article(noun: str) -> str:
    return f"{'an' if noun[0] in 'aeiou' else 'a'} {noun}"


def _describe(intent: BookingIntent) -> str:
    parts = []
    if intent.weekdays:
        parts.append("on " + ", ".join(d.capitalize() for d in intent.weekdays))
    if intent.part_of_day != "any":
        parts.append(f"in the {intent.part_of_day}")
    if intent.when == "this_week":
        parts.append("this week")
    elif intent.when == "next_week":
        parts.append("next week")
    elif intent.when == "on_date" and intent.date_from:
        parts.append(f"on {intent.date_from:%A} {intent.date_from.day} {intent.date_from:%B}")
    return " ".join(parts)


class BookingAssistant:
    def __init__(
        self,
        provider: LLMProvider,
        store: BookingStore,
        rules: SlotRules,
        clock: Callable[[], datetime],
    ) -> None:
        self._provider = provider
        self._store = store
        self._rules = rules
        self._clock = clock

    def today(self) -> date:
        return self._clock().astimezone(self._rules.tz).date()

    def _search(
        self, service: Service, first: date, last: date, intent: BookingIntent | None
    ) -> list[datetime]:
        now = self._clock()
        window_start = datetime.combine(first, time(0), tzinfo=self._rules.tz)
        window_end = datetime.combine(last + timedelta(days=1), time(0), tzinfo=self._rules.tz)
        booked = self._store.busy(window_start, window_end)
        return find_slots(
            service,
            first,
            last,
            now,
            booked,
            self._rules,
            part=intent.part_of_day if intent else "any",
            weekdays=intent.weekday_numbers() if intent else None,
        )

    def offer(self, service: Service, slots: list[datetime], text: str) -> Proposal:
        return Proposal(
            text=text,
            service=service.key,
            service_label=service.label,
            slots=[SlotOffer(s.isoformat(), format_slot(s)) for s in slots],
        )

    async def propose(
        self, message: str, history: list[Message], forced: bool = False
    ) -> Proposal | None:
        """Return open times for a booking request, or None if the message isn't one.

        `forced` is set when the patient pressed the booking button, so the message is
        treated as a booking request even if the model is unsure.
        """
        today = self.today()
        intent = await extract_intent(self._provider, message, history, today)
        if not intent.wants_appointment and not forced:
            return None

        if not intent.service_known():
            return Proposal(
                text=(
                    "Which appointment would you like? You can book these in the chat. For "
                    f"anything else, such as fillings or root canal treatment, call {CLINIC_PHONE}."
                ),
                choices=[{"key": s.key, "label": s.label} for s in SERVICES.values()],
            )

        service = SERVICES[intent.service]
        first, last = intent.window(today, self._rules.horizon.days)
        name = _with_article(service.label.lower())
        wanted = _describe(intent)
        slots = self._search(service, first, last, intent) if first <= last else []
        if slots:
            when = f" {wanted}" if wanted else ""
            return self.offer(
                service,
                slots,
                f"Here are open times for {name}{when}. Pick one and we'll hold it for you.",
            )

        soonest = self._search(service, today, today + self._rules.horizon, None)
        if soonest:
            missed = f" {wanted}" if wanted else " for the times you asked for"
            return self.offer(
                service,
                soonest,
                f"There are no openings for {name}{missed}. These are the next available.",
            )
        return Proposal(
            text=(
                f"There are no open times for {name} in the next two weeks that can be booked "
                f"online. Please call {CLINIC_PHONE} and the team will find you a time."
            ),
            service=service.key,
            service_label=service.label,
        )
