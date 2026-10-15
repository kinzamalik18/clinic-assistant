from __future__ import annotations

from pathlib import Path

import pytest

from app.chat.prompts import NOT_COVERED_REPLY
from app.chat.service import ChatService
from app.config import BACKEND_DIR
from app.knowledge.documents import load_chunks
from app.knowledge.retrieval import BM25Retriever
from app.llm.base import Message
from tests.fakes import FakeProvider

pytestmark = pytest.mark.anyio

RETRIEVER = BM25Retriever(load_chunks(Path(BACKEND_DIR / "data" / "clinic")))


def service(provider: FakeProvider) -> ChatService:
    return ChatService(RETRIEVER, provider, top_k=4, min_score=2.0)


async def collect(
    svc: ChatService, question: str, history: list[Message] | None = None
) -> tuple[str, str]:
    plan = svc.plan(question, history or [])
    text = "".join([piece async for piece in svc.stream(plan)])
    return plan.kind, text


async def test_answer_is_streamed_with_sources_and_documents_in_prompt() -> None:
    provider = FakeProvider(pieces=["A cleaning ", "costs $95 [1]."])
    svc = service(provider)
    plan = svc.plan("How much is a cleaning?", [])
    assert plan.kind == "answer"
    assert plan.sources[0].id == "services-and-prices#check-ups-and-cleanings"

    text = "".join([p async for p in svc.stream(plan)])
    assert text == "A cleaning costs $95 [1]."
    prompt = provider.calls[0][1][-1].content
    assert "<documents>" in prompt and "$95" in prompt
    assert "<question>\nHow much is a cleaning?\n</question>" in prompt


async def test_emergency_never_calls_the_model() -> None:
    provider = FakeProvider(reply="should not be used")
    kind, text = await collect(service(provider), "the bleeding won't stop after my extraction")
    assert kind == "emergency"
    assert "911" in text
    assert provider.calls == []


async def test_unrelated_question_is_not_covered_without_model_call() -> None:
    provider = FakeProvider(reply="Paris")
    kind, text = await collect(service(provider), "What is the capital of France?")
    assert kind == "not_covered"
    assert text == NOT_COVERED_REPLY
    assert provider.calls == []


@pytest.mark.parametrize(
    "pieces", [["NOT_COVERED"], ["NOT_", "COV", "ERED"], ["  NOT_COVERED\n"], []]
)
async def test_model_marker_is_replaced_and_never_shown(pieces: list[str]) -> None:
    svc = service(FakeProvider(pieces=pieces))
    plan = svc.plan("Do you offer veneers for a cleaning price?", [])
    assert plan.kind == "answer"
    text = "".join([p async for p in svc.stream(plan)])
    assert "NOT_COVERED" not in text
    assert text == NOT_COVERED_REPLY
    assert plan.kind == "not_covered"
    assert plan.sources == []


async def test_reply_starting_like_marker_is_not_swallowed() -> None:
    svc = service(FakeProvider(pieces=["N", "o, we don't accept HMO plans [1]."]))
    plan = svc.plan("Do you accept HMO dental plans?", [])
    text = "".join([p async for p in svc.stream(plan)])
    assert text == "No, we don't accept HMO plans [1]."
    assert plan.kind == "answer"


async def test_follow_up_uses_previous_question_for_retrieval() -> None:
    svc = service(FakeProvider(reply="ok"))
    history = [
        Message(role="user", content="Do you do dental implants?"),
        Message(role="assistant", content="Yes [1]."),
    ]
    plan = svc.plan("how long does that take", history)
    assert plan.kind == "answer"
    assert any(s.id == "services-and-prices#dental-implants" for s in plan.sources)


async def test_new_topic_after_history_is_not_mixed_up() -> None:
    svc = service(FakeProvider(reply="ok"))
    history = [Message(role="user", content="Do you do dental implants?")]
    plan = svc.plan("Do you accept Delta Dental PPO insurance?", history)
    assert plan.sources[0].id == "insurance-and-payment#accepted-insurance-plans"


async def test_history_is_trimmed() -> None:
    provider = FakeProvider(reply="ok")
    svc = service(provider)
    history = [Message(role="user", content="x" * 5000)] * 10
    plan = svc.plan("How much is whitening?", history)
    assert len(plan.messages) == 7
    assert all(len(m.content) <= 1000 for m in plan.messages[:-1])
