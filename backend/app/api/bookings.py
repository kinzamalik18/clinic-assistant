"""Booking a held time from the chat (public) and reviewing bookings (staff)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AwareDatetime, BaseModel

from app.api.deps import Email, Honeypot, Name, Phone, enforce, require_staff
from app.scheduling.assistant import format_slot
from app.scheduling.clinic import SERVICES
from app.scheduling.slots import SlotRules, is_bookable
from app.scheduling.store import BookingStore, NewBooking

router = APIRouter()

ServiceKey = Literal[
    "checkup",
    "cleaning",
    "checkup_and_cleaning",
    "new_patient_exam",
    "whitening",
    "implant_consultation",
]


class BookingForm(BaseModel):
    service: ServiceKey
    start: AwareDatetime
    name: Name
    email: Email
    phone: Phone | None = None
    website: Honeypot = ""


def get_bookings(request: Request) -> BookingStore:
    store: BookingStore = request.app.state.booking_store
    return store


def present(row: dict[str, Any], rules: SlotRules) -> dict[str, Any]:
    """Add labels in clinic time so the browser never has to convert time zones."""
    start = datetime.fromisoformat(row["starts_at"]).astimezone(rules.tz)
    service = SERVICES.get(row["service"])
    return {
        **row,
        "service_label": service.label if service else row["service"],
        "when": format_slot(start),
        "local_start": start.isoformat(),
    }


@router.post("/api/bookings", status_code=status.HTTP_201_CREATED)
def request_booking(
    form: BookingForm,
    request: Request,
    store: Annotated[BookingStore, Depends(get_bookings)],
) -> dict[str, str]:
    enforce(request.app.state.booking_limiter, request)
    rules: SlotRules = request.app.state.slot_rules
    clock: Callable[[], datetime] = request.app.state.clock
    service = SERVICES[form.service]
    start = form.start.astimezone(rules.tz)
    label = format_slot(start)
    if form.website:
        # Spam bot: answer as if it worked so it learns nothing, and store nothing.
        return {"status": "requested", "when": label, "service_label": service.label}
    if not is_bookable(service, start, clock(), rules):
        raise HTTPException(
            422,  # the status constant was renamed in newer Starlette versions
            "That time can't be booked online. Please pick one of the times offered.",
        )
    booking_id = store.create(
        NewBooking(
            service=service.key,
            start=start,
            end=start + timedelta(minutes=service.minutes),
            name=form.name,
            email=form.email,
            phone=form.phone or None,
        )
    )
    if booking_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Someone just took that time. Please pick another one."
        )
    return {"status": "requested", "when": label, "service_label": service.label}


staff = APIRouter(prefix="/api/staff/bookings", dependencies=[Depends(require_staff)])

BookingStatus = Literal["requested", "confirmed", "declined", "cancelled"]


@staff.get("")
def list_bookings(
    request: Request,
    store: Annotated[BookingStore, Depends(get_bookings)],
    status: BookingStatus | None = None,
) -> list[dict[str, Any]]:
    rules: SlotRules = request.app.state.slot_rules
    return [present(row, rules) for row in store.list_bookings(status)]


def _change(
    request: Request,
    store: BookingStore,
    booking_id: int,
    allowed: tuple[str, ...],
    new_status: str,
) -> dict[str, Any]:
    if store.get(booking_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if not store.transition(booking_id, allowed, new_status):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This booking can't be {new_status} now")
    row = store.get(booking_id)
    assert row is not None
    # Emailing the patient is out of scope for the demo; the status change is the record.
    return present(row, request.app.state.slot_rules)


@staff.post("/{booking_id}/confirm")
def confirm(
    booking_id: int, request: Request, store: Annotated[BookingStore, Depends(get_bookings)]
) -> dict[str, Any]:
    return _change(request, store, booking_id, ("requested",), "confirmed")


@staff.post("/{booking_id}/decline")
def decline(
    booking_id: int, request: Request, store: Annotated[BookingStore, Depends(get_bookings)]
) -> dict[str, Any]:
    return _change(request, store, booking_id, ("requested",), "declined")


@staff.post("/{booking_id}/cancel")
def cancel(
    booking_id: int, request: Request, store: Annotated[BookingStore, Depends(get_bookings)]
) -> dict[str, Any]:
    return _change(request, store, booking_id, ("requested", "confirmed"), "cancelled")


router.include_router(staff)
