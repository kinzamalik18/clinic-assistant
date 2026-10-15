from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import create_app
from tests.fakes import FakeProvider
from tests.helpers import make_settings

ClientFactory = Callable[..., TestClient]

AUTH = {"authorization": "Bearer test-staff-token"}

TRIAGE = json.dumps(
    {
        "category": "appointment_request",
        "priority": "normal",
        "summary": "Wants a cleaning next week.",
        "draft_reply": "Hi Sam, thanks for getting in touch.",
    }
)

FORM = {
    "name": "Sam Lee",
    "email": "sam@example.com",
    "subject": "Cleaning",
    "message": "I'd like to book a cleaning next week please.",
}


@pytest.fixture
def make_client(tmp_path: Path) -> ClientFactory:
    def factory(provider: FakeProvider | None = None, **overrides: object) -> TestClient:
        settings = make_settings(tmp_path, **overrides)
        return TestClient(create_app(settings, provider=provider or FakeProvider(reply=TRIAGE)))

    return factory


def test_submitted_message_is_triaged_and_awaits_review(make_client: ClientFactory) -> None:
    with make_client() as c:
        assert c.post("/api/messages", json=FORM).json() == {"status": "received"}
        messages = c.get("/api/staff/messages", headers=AUTH).json()
        assert len(messages) == 1
        detail = c.get(f"/api/staff/messages/{messages[0]['id']}", headers=AUTH).json()
    assert detail["status"] == "needs_review"
    assert detail["category"] == "appointment_request"
    assert detail["draft_reply"].startswith("Hi Sam")


def test_staff_endpoints_need_a_valid_token(make_client: ClientFactory) -> None:
    with make_client() as c:
        assert c.get("/api/staff/messages").status_code == 401
        bad = {"authorization": "Bearer wrong-token-wrong-token"}
        assert c.get("/api/staff/messages", headers=bad).status_code == 401
        assert (
            c.get("/api/staff/stats", headers={"authorization": "test-staff-token"}).status_code
            == 401
        )
        assert c.get("/api/staff/stats", headers=AUTH).status_code == 200


@pytest.mark.parametrize("token", ["", "short"])
def test_staff_access_is_disabled_without_a_strong_token(
    make_client: ClientFactory, token: str
) -> None:
    with make_client(staff_token=SecretStr(token)) as c:
        response = c.get("/api/staff/messages", headers={"authorization": f"Bearer {token}"})
    assert response.status_code == 503


def test_approve_records_edits_and_cannot_happen_twice(make_client: ClientFactory) -> None:
    with make_client() as c:
        c.post("/api/messages", json=FORM)
        c.post("/api/messages", json=FORM)
        first, second = sorted(m["id"] for m in c.get("/api/staff/messages", headers=AUTH).json())

        unchanged = c.post(
            f"/api/staff/messages/{first}/approve",
            json={"reply": "Hi Sam, thanks for getting in touch.  "},
            headers=AUTH,
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["status"] == "sent" and unchanged.json()["edited"] == 0

        edited = c.post(
            f"/api/staff/messages/{second}/approve",
            json={"reply": "Hi Sam, we have Tuesday at 10am free."},
            headers=AUTH,
        )
        assert edited.json()["edited"] == 1

        again = c.post(f"/api/staff/messages/{first}/approve", json={"reply": "x"}, headers=AUTH)
        assert again.status_code == 409
        assert c.post(f"/api/staff/messages/{first}/reject", headers=AUTH).status_code == 409

        stats = c.get("/api/staff/stats", headers=AUTH).json()
    assert stats["sent"] == 2 and stats["sent_without_edits"] == 1
    assert stats["by_status"]["sent"] == 2


def test_failed_triage_can_be_retried(make_client: ClientFactory) -> None:
    provider = FakeProvider(fail=True)
    with make_client(provider=provider) as c:
        c.post("/api/messages", json=FORM)
        message_id = c.get("/api/staff/messages", headers=AUTH).json()[0]["id"]
        assert (
            c.get(f"/api/staff/messages/{message_id}", headers=AUTH).json()["status"]
            == "triage_failed"
        )

        provider.fail = False
        provider.reply = TRIAGE
        assert c.post(f"/api/staff/messages/{message_id}/retry", headers=AUTH).status_code == 202
        assert (
            c.get(f"/api/staff/messages/{message_id}", headers=AUTH).json()["status"]
            == "needs_review"
        )
        assert c.post(f"/api/staff/messages/{message_id}/retry", headers=AUTH).status_code == 409


def test_failed_triage_can_still_be_answered_by_hand(make_client: ClientFactory) -> None:
    with make_client(provider=FakeProvider(fail=True)) as c:
        c.post("/api/messages", json=FORM)
        message_id = c.get("/api/staff/messages", headers=AUTH).json()[0]["id"]
        reply = c.post(
            f"/api/staff/messages/{message_id}/approve", json={"reply": "Hi"}, headers=AUTH
        )
    assert reply.json()["status"] == "sent" and reply.json()["edited"] == 1


def test_honeypot_submissions_are_dropped_silently(make_client: ClientFactory) -> None:
    with make_client() as c:
        response = c.post("/api/messages", json={**FORM, "website": "http://spam.example"})
        assert response.json() == {"status": "received"}
        assert c.get("/api/staff/messages", headers=AUTH).json() == []


@pytest.mark.parametrize(
    "change",
    [
        {"email": "not-an-email"},
        {"message": "short"},
        {"name": "   "},
        {"message": "x" * 3001},
    ],
)
def test_contact_form_validation(make_client: ClientFactory, change: dict[str, str]) -> None:
    with make_client() as c:
        assert c.post("/api/messages", json={**FORM, **change}).status_code == 422


def test_contact_form_rate_limit(make_client: ClientFactory) -> None:
    with make_client(contact_rate_limit_per_hour=2) as c:
        codes = [c.post("/api/messages", json=FORM).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_unknown_message_and_bad_status_filter(make_client: ClientFactory) -> None:
    with make_client() as c:
        assert c.get("/api/staff/messages/999", headers=AUTH).status_code == 404
        assert c.get("/api/staff/messages?status=bogus", headers=AUTH).status_code == 422
