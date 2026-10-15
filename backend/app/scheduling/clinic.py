"""What can be booked, how long it takes, and when the clinic is open.

These values mirror backend/data/clinic. Keep both in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    minutes: int
    saturday: bool  # Saturdays are for check-ups, cleanings and urgent care only.


SERVICES: dict[str, Service] = {
    s.key: s
    for s in (
        Service("checkup", "Check-up", 20, saturday=True),
        Service("cleaning", "Cleaning", 40, saturday=True),
        Service("checkup_and_cleaning", "Check-up and cleaning", 60, saturday=True),
        Service("new_patient_exam", "New patient examination", 45, saturday=False),
        Service("whitening", "In-clinic whitening", 90, saturday=False),
        Service("implant_consultation", "Implant consultation", 20, saturday=False),
    )
}

# Keyed by date.weekday(): Monday is 0. Sunday is closed.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    0: (time(8), time(18)),
    1: (time(8), time(18)),
    2: (time(8), time(18)),
    3: (time(8), time(18)),
    4: (time(8), time(16)),
    5: (time(9), time(13)),
}

SATURDAY = 5
SLOT_STEP_MINUTES = 15
