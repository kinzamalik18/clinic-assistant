from __future__ import annotations

import pytest

from app.safety import Severity, check_message


@pytest.mark.parametrize(
    "text",
    [
        "I can't breathe properly and my face is swollen",
        "my swelling has spread up to my eye",
        "The bleeding won't stop after my extraction",
        "I think I broke my jaw playing football",
        "having chest pain and toothache",
    ],
)
def test_emergencies(text: str) -> None:
    flag = check_message(text)
    assert flag is not None and flag.severity is Severity.EMERGENCY


@pytest.mark.parametrize(
    "text",
    [
        "my son's tooth got knocked out",
        "I chipped my front tooth on a fork",
        "severe tooth pain since last night",
        "my gum is swollen near the back tooth",
        "I have a fever and toothache",
    ],
)
def test_urgent(text: str) -> None:
    flag = check_message(text)
    assert flag is not None and flag.severity is Severity.URGENT


@pytest.mark.parametrize(
    "text",
    ["How much ibuprofen can I take?", "do I need antibiotics after a root canal"],
)
def test_medication(text: str) -> None:
    flag = check_message(text)
    assert flag is not None and flag.severity is Severity.MEDICATION


@pytest.mark.parametrize(
    "text",
    [
        "How much is a cleaning?",
        "Do you accept Delta Dental?",
        "What are your opening hours on Saturday?",
        "Can I bring my kids?",
    ],
)
def test_ordinary_questions_are_not_flagged(text: str) -> None:
    assert check_message(text) is None


def test_emergency_outranks_urgent() -> None:
    flag = check_message("my tooth was knocked out in a car accident")
    assert flag is not None and flag.severity is Severity.EMERGENCY
