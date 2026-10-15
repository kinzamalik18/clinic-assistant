"""Measure the chatbot and inbox triage against the labeled sets in this folder.

Offline (default): retrieval, routing and the safety rules. No API calls.
    python -m eval.run_eval

Online: also runs the real model for every question and message. Needs an API key
in .env and uses roughly 75 model calls.
    python -m eval.run_eval --online
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.chat.service import ChatService
from app.config import get_settings
from app.inbox.triage import Category, Priority, Triager
from app.knowledge.documents import load_chunks
from app.knowledge.retrieval import BM25Retriever
from app.llm.base import LLMError
from app.llm.fallback import build_provider
from app.safety import Severity, check_message

HERE = Path(__file__).resolve().parent
CITATION = re.compile(r"\[\d+\]")


def load(name: str) -> list[dict[str, Any]]:
    lines = (HERE / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.0f}%)" if whole else "n/a"


@dataclass
class Row:
    label: str
    value: str


def offline(service: ChatService, top_k: int) -> tuple[list[Row], list[str]]:
    questions = load("questions.jsonl")
    messages = load("messages.jsonl")
    misses: list[str] = []

    safety = [q for q in questions if q["expect"] not in ("answer", "not_covered")]
    answerable = [q for q in questions if q["expect"] == "answer"]
    safe_ok = 0
    for q in safety:
        if service.plan(q["question"], []).kind == q["expect"]:
            safe_ok += 1
        else:
            misses.append(f"safety: {q['question']!r} expected {q['expect']}")

    hit_1 = hit_k = refused = 0
    for q in answerable:
        plan = service.plan(q["question"], [])
        ids = [s.id for s in plan.sources]
        if plan.kind == "not_covered":
            refused += 1
            misses.append(f"threshold refused: {q['question']!r}")
        if ids[:1] and ids[0] in q["sources"]:
            hit_1 += 1
        if any(i in q["sources"] for i in ids[:top_k]):
            hit_k += 1
        elif plan.kind == "answer":
            misses.append(f"retrieval: {q['question']!r} got {ids[:2]}")

    out_of_scope = [q for q in questions if q["expect"] == "not_covered"]
    gated = sum(1 for q in out_of_scope if service.plan(q["question"], []).kind == "not_covered")

    urgent_true = [m for m in messages if m["urgent"]]
    urgent_false = [m for m in messages if not m["urgent"]]

    def flagged(m: dict[str, Any]) -> bool:
        flag = check_message(f"{m['subject']}\n{m['body']}")
        return flag is not None and flag.severity in (Severity.EMERGENCY, Severity.URGENT)

    caught = sum(1 for m in urgent_true if flagged(m))
    false_alarms = [m for m in urgent_false if flagged(m)]
    misses += [f"safety false alarm: {m['body'][:60]!r}" for m in false_alarms]

    let_through = [
        q["question"] for q in out_of_scope if service.plan(q["question"], []).kind != "not_covered"
    ]
    misses += [f"reaches the model (it must reply NOT_COVERED): {q!r}" for q in let_through]

    rows = [
        Row("Safety questions given the right fixed reply", pct(safe_ok, len(safety))),
        Row("Answerable: right section ranked first", pct(hit_1, len(answerable))),
        Row(f"Answerable: right section in top {top_k}", pct(hit_k, len(answerable))),
        Row("Answerable but stopped by the retrieval threshold", pct(refused, len(answerable))),
        Row("Out-of-scope questions stopped before the model", pct(gated, len(out_of_scope))),
        Row("Urgent contact messages caught by the safety rules", pct(caught, len(urgent_true))),
        Row(
            "Non-urgent messages wrongly flagged urgent",
            pct(len(false_alarms), len(urgent_false)),
        ),
    ]
    return rows, misses


async def online(
    service: ChatService, triager: Triager, delay: float
) -> tuple[list[Row], list[str]]:
    questions = load("questions.jsonl")
    messages = load("messages.jsonl")
    misses: list[str] = []

    correct = cited = answered = errors = 0
    for q in questions:
        plan = service.plan(q["question"], [])
        try:
            text = "".join([piece async for piece in service.stream(plan)])
        except LLMError as exc:
            errors += 1
            misses.append(f"chat error: {q['question']!r}: {exc}")
            continue
        if plan.kind == q["expect"]:
            correct += 1
        else:
            misses.append(f"chat: {q['question']!r} expected {q['expect']}, got {plan.kind}")
        if plan.kind == "answer":
            answered += 1
            cited += bool(CITATION.search(text))
        if plan.fixed_text is None:
            await asyncio.sleep(delay)

    right_category = urgent_ok = triage_errors = 0
    for m in messages:
        try:
            result = await triager.triage(m["name"], m["subject"], m["body"])
        except LLMError as exc:
            triage_errors += 1
            misses.append(f"triage error: {m['subject']!r}: {exc}")
            continue
        if result.category == Category(m["category"]):
            right_category += 1
        else:
            misses.append(
                f"triage: {m['body'][:50]!r} expected {m['category']}, got {result.category.value}"
            )
        urgent_ok += (result.priority is Priority.URGENT) == m["urgent"]
        await asyncio.sleep(delay)

    rows = [
        Row("Chat: final reply type matches the label", pct(correct, len(questions))),
        Row("Chat: answers that cite a source", pct(cited, answered)),
        Row("Chat: model errors", str(errors)),
        Row("Triage: category matches the label", pct(right_category, len(messages))),
        Row("Triage: urgent or not, correct", pct(urgent_ok, len(messages))),
        Row("Triage: model errors", str(triage_errors)),
    ]
    return rows, misses


def print_table(title: str, rows: list[Row]) -> None:
    print(f"\n### {title}\n")
    print("| Measure | Result |\n| --- | --- |")
    for row in rows:
        print(f"| {row.label} | {row.value} |")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--online", action="store_true", help="also call the real model")
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between model calls")
    parser.add_argument("--show-misses", action="store_true", help="list every failed case")
    args = parser.parse_args()

    settings = get_settings()
    retriever = BM25Retriever(load_chunks(settings.resolve(settings.knowledge_dir)))
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        provider = build_provider(settings, client)
        service = ChatService(
            retriever, provider, settings.retrieval_top_k, settings.retrieval_min_score
        )
        rows, misses = offline(service, settings.retrieval_top_k)
        print_table("Offline: retrieval, routing and safety rules", rows)
        if args.online:
            if provider.name == "none":
                raise SystemExit("No API key found. Add GEMINI_API_KEY or GROQ_API_KEY to .env.")
            online_rows, online_misses = await online(
                service, Triager(provider, retriever), args.delay
            )
            print_table(f"Online: full pipeline with {provider.name}", online_rows)
            misses += online_misses

    if args.show_misses and misses:
        print("\n### Misses\n")
        for miss in misses:
            print(f"- {miss}")


if __name__ == "__main__":
    asyncio.run(main())
