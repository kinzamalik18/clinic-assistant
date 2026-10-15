"""Patient chat: safety check, retrieval, then a grounded and cited answer."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.chat.prompts import NOT_COVERED, NOT_COVERED_REPLY, SYSTEM_PROMPT, build_user_turn
from app.knowledge.retrieval import Retriever, ScoredChunk
from app.llm.base import LLMProvider, Message
from app.safety import FIXED_REPLIES, check_message

MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 1000

# Words that usually point back to an earlier message, as in "how much is that?".
_FOLLOW_UP = re.compile(r"\b(it|its|that|this|those|these|them|they|one)\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)

ReplyKind = Literal["answer", "not_covered", "emergency", "urgent", "medication"]


@dataclass(frozen=True)
class Source:
    number: int
    id: str
    title: str
    section: str
    text: str


@dataclass
class ChatPlan:
    """What the service decided to do before any text is generated."""

    kind: ReplyKind
    sources: list[Source] = field(default_factory=list)
    fixed_text: str | None = None
    messages: list[Message] = field(default_factory=list)


def _sources(results: list[ScoredChunk]) -> list[Source]:
    return [
        Source(
            number=i,
            id=r.chunk.id,
            title=r.chunk.doc_title,
            section=r.chunk.section,
            text=r.chunk.text,
        )
        for i, r in enumerate(results, start=1)
    ]


class ChatService:
    def __init__(
        self, retriever: Retriever, provider: LLMProvider, top_k: int, min_score: float
    ) -> None:
        self._retriever = retriever
        self._provider = provider
        self._top_k = top_k
        self._min_score = min_score

    def retrieve(self, question: str, history: list[Message]) -> list[ScoredChunk]:
        """Find document sections for a question, using the previous question for follow-ups.

        A follow-up such as "how long does that take?" is searched together with the
        previous user message. Any other question that finds nothing on its own also gets
        a second try with the previous message added.
        """
        previous = next((m.content for m in reversed(history) if m.role == "user"), None)
        is_follow_up = previous is not None and (
            bool(_FOLLOW_UP.search(question)) or len(_WORD.findall(question)) <= 3
        )
        queries = [f"{previous} {question}"] if is_follow_up else [question]
        if previous and not is_follow_up:
            queries.append(f"{previous} {question}")
        for query in queries:
            results = self._retriever.search(query, self._top_k)
            if results and results[0].score >= self._min_score:
                return results
        return []

    def plan(self, question: str, history: list[Message]) -> ChatPlan:
        flag = check_message(question)
        if flag is not None:
            return ChatPlan(kind=flag.severity.value, fixed_text=FIXED_REPLIES[flag.severity])

        results = self.retrieve(question, history)
        if not results:
            return ChatPlan(kind="not_covered", fixed_text=NOT_COVERED_REPLY)

        recent = [
            Message(role=m.role, content=m.content[:MAX_HISTORY_CHARS])
            for m in history[-MAX_HISTORY_MESSAGES:]
        ]
        messages = [*recent, Message(role="user", content=build_user_turn(question, results))]
        return ChatPlan(kind="answer", sources=_sources(results), messages=messages)

    async def stream(self, plan: ChatPlan) -> AsyncIterator[str]:
        """Yield answer text. A model reply of NOT_COVERED is replaced by the fixed reply.

        The first few characters are held back until we know the reply is not the
        marker, so the marker itself never reaches the patient. Callers should check
        `plan.kind` after the stream ends, because it can change to "not_covered".
        """
        if plan.fixed_text is not None:
            yield plan.fixed_text
            return

        buffer = ""
        decided = False
        async for piece in self._provider.stream(SYSTEM_PROMPT, plan.messages, temperature=0.1):
            if decided:
                yield piece
                continue
            buffer += piece
            stripped = buffer.lstrip()
            if len(stripped) < len(NOT_COVERED) and NOT_COVERED.startswith(stripped):
                continue  # might still be the marker
            decided = True
            if stripped.startswith(NOT_COVERED):
                break
            yield buffer

        if not decided or buffer.lstrip().startswith(NOT_COVERED):
            plan.kind = "not_covered"
            plan.sources = []
            yield NOT_COVERED_REPLY
