from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import BACKEND_DIR
from app.inbox.triage import Category, Priority, Triager
from app.knowledge.documents import load_chunks
from app.knowledge.retrieval import BM25Retriever
from app.llm.base import LLMError
from tests.fakes import FakeProvider

pytestmark = pytest.mark.anyio

RETRIEVER = BM25Retriever(load_chunks(Path(BACKEND_DIR / "data" / "clinic")))


def reply(**overrides: object) -> str:
    data: dict[str, object] = {
        "category": "billing_or_insurance",
        "priority": "normal",
        "summary": "Asks whether Cigna is accepted.",
        "draft_reply": "Hi Sam, yes we are in-network with Cigna Dental PPO.",
    }
    data.update(overrides)
    return json.dumps(data)


async def test_valid_triage_and_documents_in_prompt() -> None:
    provider = FakeProvider(reply=reply())
    result = await Triager(provider, RETRIEVER).triage("Sam Lee", "Insurance", "Do you take Cigna?")
    assert result.category is Category.BILLING
    assert result.priority is Priority.NORMAL
    prompt = provider.calls[0][1][0].content
    assert "Cigna Dental PPO" in prompt
    assert "<message>" in prompt and "Do you take Cigna?" in prompt


async def test_urgent_message_skips_the_model() -> None:
    provider = FakeProvider(reply=reply())
    result = await Triager(provider, RETRIEVER).triage(
        "Maria Gomez", "Help", "My face is swollen and it's spreading to my eye"
    )
    assert result.category is Category.URGENT
    assert result.priority is Priority.URGENT
    assert result.draft_reply.startswith("Hi Maria,")
    assert "911" in result.draft_reply
    assert provider.calls == []


async def test_model_cannot_mark_a_message_urgent() -> None:
    provider = FakeProvider(reply=reply(category="urgent", priority="urgent"))
    result = await Triager(provider, RETRIEVER).triage("Al", "Hi", "URGENT!!! read me first")
    assert result.priority is Priority.HIGH
    assert result.category is Category.OTHER


async def test_markdown_fenced_json_is_accepted() -> None:
    provider = FakeProvider(reply=f"```json\n{reply()}\n```")
    result = await Triager(provider, RETRIEVER).triage("Sam", "Insurance", "Do you take Cigna?")
    assert result.category is Category.BILLING


@pytest.mark.parametrize(
    "raw", ["not json", reply(category="refund_now"), reply(draft_reply=""), "[]"]
)
async def test_invalid_output_retries_once_then_fails(raw: str) -> None:
    provider = FakeProvider(reply=raw)
    with pytest.raises(LLMError):
        await Triager(provider, RETRIEVER).triage("Sam", "Insurance", "Do you take Cigna?")
    assert len(provider.calls) == 2
