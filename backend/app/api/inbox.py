"""Contact form (public) and the staff review queue (token protected)."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import enforce
from app.inbox.store import MessageStore
from app.inbox.triage import Triager
from app.llm.base import LLMError

logger = logging.getLogger(__name__)
router = APIRouter()

MIN_STAFF_TOKEN_LENGTH = 16

Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class ContactForm(BaseModel):
    name: Annotated[Text, StringConstraints(min_length=1, max_length=100)]
    email: Annotated[Text, StringConstraints(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    phone: Annotated[Text, StringConstraints(max_length=30)] | None = None
    subject: Annotated[Text, StringConstraints(min_length=1, max_length=150)]
    message: Annotated[Text, StringConstraints(min_length=10, max_length=3000)]
    # Hidden field on the form. People never fill it in; simple spam bots usually do.
    website: str = Field(default="", max_length=200)


class ApproveRequest(BaseModel):
    reply: Annotated[Text, StringConstraints(min_length=1, max_length=4000)]


def get_store(request: Request) -> MessageStore:
    store: MessageStore = request.app.state.store
    return store


def require_staff(request: Request) -> None:
    expected = request.app.state.settings.staff_token.get_secret_value()
    if len(expected) < MIN_STAFF_TOKEN_LENGTH:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Staff access is disabled. Set STAFF_TOKEN (16+ characters) on the server.",
        )
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid staff token",
            headers={"www-authenticate": "Bearer"},
        )


async def run_triage(store: MessageStore, triager: Triager, message_id: int) -> None:
    message = store.get(message_id)
    if message is None or message["status"] != "new":
        return
    try:
        result = await triager.triage(message["name"], message["subject"], message["body"])
    except LLMError as exc:
        logger.error("Triage failed for message %s: %s", message_id, exc)
        store.mark_failed(message_id)
        return
    store.save_triage(message_id, result)


@router.post("/api/messages", status_code=status.HTTP_202_ACCEPTED)
def submit_message(
    form: ContactForm,
    request: Request,
    background: BackgroundTasks,
    store: Annotated[MessageStore, Depends(get_store)],
) -> dict[str, str]:
    enforce(request.app.state.contact_limiter, request)
    if form.website:
        logger.info("Dropped a contact form submission that filled the honeypot field")
    else:
        message_id = store.create(
            form.name, form.email, form.phone or None, form.subject, form.message
        )
        background.add_task(run_triage, store, request.app.state.triager, message_id)
    # Same answer either way, so bots learn nothing from the response.
    return {"status": "received"}


staff = APIRouter(prefix="/api/staff", dependencies=[Depends(require_staff)])

StatusFilter = Literal["new", "needs_review", "triage_failed", "sent", "rejected"]


def _found(message: dict[str, Any] | None) -> dict[str, Any]:
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return message


@staff.get("/messages")
def list_messages(
    store: Annotated[MessageStore, Depends(get_store)], status: StatusFilter | None = None
) -> list[dict[str, Any]]:
    return store.list_messages(status)


@staff.get("/messages/{message_id}")
def get_message(
    message_id: int, store: Annotated[MessageStore, Depends(get_store)]
) -> dict[str, Any]:
    return _found(store.get(message_id))


@staff.post("/messages/{message_id}/approve")
def approve(
    message_id: int, body: ApproveRequest, store: Annotated[MessageStore, Depends(get_store)]
) -> dict[str, Any]:
    _found(store.get(message_id))
    if not store.approve(message_id, body.reply):
        raise HTTPException(status.HTTP_409_CONFLICT, "This message is not awaiting review")
    # Sending email is out of scope for the demo; the approved reply is stored as sent.
    return _found(store.get(message_id))


@staff.post("/messages/{message_id}/reject")
def reject(message_id: int, store: Annotated[MessageStore, Depends(get_store)]) -> dict[str, Any]:
    _found(store.get(message_id))
    if not store.reject(message_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "This message is not awaiting review")
    return _found(store.get(message_id))


@staff.post("/messages/{message_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry(
    message_id: int,
    request: Request,
    background: BackgroundTasks,
    store: Annotated[MessageStore, Depends(get_store)],
) -> dict[str, str]:
    _found(store.get(message_id))
    if not store.reset_for_retry(message_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed triage can be retried")
    background.add_task(run_triage, store, request.app.state.triager, message_id)
    return {"status": "retrying"}


@staff.get("/stats")
def stats(store: Annotated[MessageStore, Depends(get_store)]) -> dict[str, Any]:
    return store.stats()


router.include_router(staff)
