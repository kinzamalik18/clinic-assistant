"""Load the clinic's Markdown documents and split them into section-sized chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SKIP_FILES = {"README.md"}


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    doc_title: str
    section: str
    text: str


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def parse_document(name: str, markdown: str) -> list[Chunk]:
    """Split one Markdown document into chunks, one per `##` section.

    Text between the `#` title and the first `##` heading becomes an "Overview" chunk.
    """
    title = name
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in markdown.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            title = line[2:].strip()
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for section, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                id=f"{name}#{_slug(section)}",
                doc=name,
                doc_title=title,
                section=section,
                text=text,
            )
        )
    return chunks


def load_chunks(directory: Path) -> list[Chunk]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Knowledge directory not found: {directory}")
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        if path.name in _SKIP_FILES:
            continue
        chunks.extend(parse_document(path.stem, path.read_text(encoding="utf-8")))
    if not chunks:
        raise ValueError(f"No document sections found in {directory}")
    return chunks
