from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.chat.citations import CitationFixer, fix_citations

pytestmark = pytest.mark.anyio


def run(*pieces: str) -> str:
    fixer = CitationFixer()
    return "".join(fixer.feed(p) for p in pieces) + fixer.flush()


@pytest.mark.parametrize(
    ("pieces", "expected"),
    [
        (["A cleaning costs $95【1】."], "A cleaning costs $95[1]."),
        (["costs $95【", "1】."], "costs $95[1]."),
        (["costs $95", "【", "2", "】", " and more"], "costs $95[2] and more"),
        (["Open at 8【1†L3-L5】."], "Open at 8[1]."),
        (["Two sources【1】【2】."], "Two sources[1][2]."),
        (["Already fine [1]."], "Already fine [1]."),
        (["A 【note】 in brackets"], "A 【note】 in brackets"),
        (["Unclosed 【1 at the end"], "Unclosed 【1 at the end"),
        (["Long 【" + "x" * 40 + "】 text"], "Long 【" + "x" * 40 + "】 text"),
    ],
)
def test_markers_become_square_brackets(pieces: list[str], expected: str) -> None:
    assert run(*pieces) == expected


async def test_stream_wrapper_keeps_text_flowing() -> None:
    async def source() -> AsyncIterator[str]:
        for piece in ["Fridays we close at 4 pm【", "2", "】", "."]:
            yield piece

    assert "".join([p async for p in fix_citations(source())]) == "Fridays we close at 4 pm[2]."
