"""Normalise citation markers in streamed model output to the [n] form the widget expects.

Some models, such as OpenAI's GPT-OSS family, write citations as 【1】 or 【1†source】
instead of [1]. The text arrives in pieces, so a marker can be split across chunks.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

OPEN, CLOSE = "【", "】"
# A real marker is short. Anything longer is ordinary text that happens to use the bracket.
MAX_MARKER = 32
_NUMBER = re.compile(r"【\s*(\d+)")


def _convert(marker: str) -> str:
    match = _NUMBER.match(marker)
    return f"[{match.group(1)}]" if match else marker


class CitationFixer:
    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        buffer, self._pending = self._pending + text, ""
        out: list[str] = []
        position = 0
        while position < len(buffer):
            start = buffer.find(OPEN, position)
            if start == -1:
                out.append(buffer[position:])
                break
            out.append(buffer[position:start])
            end = buffer.find(CLOSE, start)
            if end == -1:
                if len(buffer) - start > MAX_MARKER:
                    out.append(buffer[start:])
                else:
                    self._pending = buffer[start:]  # wait for the rest of the marker
                break
            if end - start > MAX_MARKER:
                out.append(buffer[start : start + 1])
                position = start + 1
                continue
            out.append(_convert(buffer[start : end + 1]))
            position = end + 1
        return "".join(out)

    def flush(self) -> str:
        rest, self._pending = self._pending, ""
        return rest


async def fix_citations(pieces: AsyncIterator[str]) -> AsyncIterator[str]:
    fixer = CitationFixer()
    async for piece in pieces:
        text = fixer.feed(piece)
        if text:
            yield text
    rest = fixer.flush()
    if rest:
        yield rest
