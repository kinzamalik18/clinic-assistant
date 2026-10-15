"""Keyword retrieval over document chunks using BM25.

BM25 needs no model download and no API calls, which keeps the service small and
predictable. Retrieval sits behind the `Retriever` protocol so an embedding-based
retriever can be swapped in and compared with the evaluation script.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from app.knowledge.documents import Chunk

_STOPWORDS = frozenset(
    """a an and are as at be but by can could do does for from had has have how i if in
    into is it its me my of on or our please should so than that the their them there
    these they this to was we what when where which who will with would you your""".split()
)
_IRREGULAR = {"teeth": "tooth", "children": "child", "kids": "child", "kid": "child"}
_TOKEN = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    """Very small suffix stripper. It only needs to be consistent, not linguistically perfect."""
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    for suffix in ("ing", "ed"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    # Single characters are dropped: they are mostly leftovers like the "s" in "what's".
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[ScoredChunk]: ...


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        if not chunks:
            raise ValueError("BM25Retriever needs at least one chunk")
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._doc_terms: list[Counter[str]] = []
        lengths: list[int] = []
        document_frequency: Counter[str] = Counter()
        for chunk in chunks:
            # The title and section heading are indexed with the body so that a
            # question like "wisdom tooth removal price" can match a section heading.
            terms = tokenize(f"{chunk.doc_title} {chunk.section} {chunk.text}")
            counts = Counter(terms)
            self._doc_terms.append(counts)
            lengths.append(len(terms))
            document_frequency.update(counts.keys())
        self._lengths = lengths
        self._avg_length = sum(lengths) / len(lengths)
        n = len(chunks)
        self._idf = {
            term: math.log(1 + (n - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    def search(self, query: str, k: int) -> list[ScoredChunk]:
        terms = set(tokenize(query))
        if not terms or k <= 0:
            return []
        results: list[ScoredChunk] = []
        for chunk, counts, length in zip(self._chunks, self._doc_terms, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf == 0:
                    continue
                norm = tf + self._k1 * (1 - self._b + self._b * length / self._avg_length)
                score += self._idf[term] * tf * (self._k1 + 1) / norm
            if score > 0:
                results.append(ScoredChunk(chunk=chunk, score=score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]
