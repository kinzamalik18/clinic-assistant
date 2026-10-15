"""Rule-based safety checks that run before any model call.

Emergencies and medication questions are handled with fixed wording instead of a
generated answer. Rules are deliberately broad: a false alarm costs a patient a few
seconds, a missed emergency could cost much more.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    EMERGENCY = "emergency"  # call emergency services now
    URGENT = "urgent"  # needs a same-day dental appointment
    MEDICATION = "medication"  # asks for medicine or dosing advice


@dataclass(frozen=True)
class SafetyFlag:
    severity: Severity
    reason: str


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


_EMERGENCY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "breathing or swallowing difficulty",
        _rx(
            r"\b(can'?t|cannot|can not|hard to|trouble|difficulty|struggling to)\s+"
            r"(breath|breathe|breathing|swallow|swallowing)",
            r"short(ness)? of breath",
        ),
    ),
    (
        "swelling spreading to the eye or neck",
        _rx(r"swell\w*\b.{0,40}\b(eye|neck|throat)", r"\b(eye|neck|throat)\b.{0,40}swell"),
    ),
    (
        "bleeding that will not stop",
        _rx(
            r"bleed\w*\s+(won'?t|will not|doesn'?t|does not|isn'?t|is not|not)\s+stop",
            r"(heavy|heavily|lots of|a lot of|severe)\s+bleed",
            r"bleed\w*\s+(heavily|a lot|badly)",
        ),
    ),
    (
        "face or jaw injury",
        _rx(
            r"\b(broke|broken|fractured?|dislocated)\s+(my\s+)?jaw",
            r"\bjaw\b.{0,30}\b(broken|injur\w*|dislocated)",
            r"\b(car|bike|sports?)\s+(accident|crash)",
        ),
    ),
    ("possible serious illness", _rx(r"\bchest pain", r"\bunconscious", r"\bpassed out")),
]

_URGENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "knocked-out or broken tooth",
        _rx(
            r"knock\w*\s+(out|off)",
            r"tooth\s+(fell|came|has fallen)\s+out",
            r"(broke|broken|cracked|chipped)\s+(a\s+|my\s+)?(front\s+)?(tooth|teeth)",
        ),
    ),
    (
        "severe pain",
        _rx(r"(severe|unbearable|excruciating|extreme|terrible)\s+(tooth|dental|jaw)?\s*pain"),
    ),
    ("swelling", _rx(r"\bswell(ing|ed|s)?\b", r"\bswollen\b", r"\babscess")),
    ("fever with dental symptoms", _rx(r"\bfever\b")),
]

_MEDICATION = _rx(
    r"\b(ibuprofen|advil|motrin|paracetamol|acetaminophen|tylenol|aspirin|naproxen)\b",
    r"\b(antibiotic|antibiotics|amoxicillin|penicillin|painkiller|pain killer)s?\b",
    r"\b(dose|dosage|how many (pills|tablets)|mg\b|milligram)",
    r"\bwhat (medicine|medication)\b",
)


def check_message(text: str) -> SafetyFlag | None:
    """Return the most serious safety flag for a message, or None."""
    for reason, pattern in _EMERGENCY_RULES:
        if pattern.search(text):
            return SafetyFlag(Severity.EMERGENCY, reason)
    for reason, pattern in _URGENT_RULES:
        if pattern.search(text):
            return SafetyFlag(Severity.URGENT, reason)
    if _MEDICATION.search(text):
        return SafetyFlag(Severity.MEDICATION, "medication question")
    return None


CLINIC_PHONE = "(555) 010-2400"
OUT_OF_HOURS_PHONE = "(555) 010-2499"

FIXED_REPLIES: dict[Severity, str] = {
    Severity.EMERGENCY: (
        "This sounds like it could be a medical emergency. Please call 911 or go to the "
        "nearest emergency room now. Don't wait for a reply from this chat."
    ),
    Severity.URGENT: (
        "This sounds urgent. Please call the clinic now on "
        f"{CLINIC_PHONE}. We keep same-day slots for pain, swelling and broken or "
        f"knocked-out teeth. If we're closed, call the out-of-hours line on {OUT_OF_HOURS_PHONE}. "
        "If you have swelling spreading to your eye or neck, or trouble breathing or "
        "swallowing, call 911."
    ),
    Severity.MEDICATION: (
        "I can't give advice about medicines or doses. Please ask a pharmacist or your "
        f"doctor, or call our front desk on {CLINIC_PHONE} to speak to a member of the team. "
        "If you are in severe pain or have swelling, call us today."
    ),
}
