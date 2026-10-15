from __future__ import annotations

from app.knowledge.documents import Chunk, parse_document
from app.knowledge.retrieval import BM25Retriever, tokenize


def test_tokenize_stems_drops_stopwords_and_stray_letters() -> None:
    assert tokenize("What's the price of cleanings for children?") == ["price", "clean", "child"]


def test_parse_document_splits_sections_and_keeps_overview() -> None:
    chunks = parse_document(
        "prices",
        "# Prices\nIntro text.\n\n## Check-ups and cleanings\nA cleaning costs $95.\n\n## Empty\n",
    )
    assert [c.id for c in chunks] == ["prices#overview", "prices#check-ups-and-cleanings"]
    assert chunks[1].doc_title == "Prices"
    assert chunks[1].text == "A cleaning costs $95."


def chunk(section: str, text: str) -> Chunk:
    return Chunk(id=section, doc="d", doc_title="Doc", section=section, text=text)


def test_search_ranks_the_matching_section_first() -> None:
    retriever = BM25Retriever(
        [
            chunk("hours", "We open at 8 am on weekdays."),
            chunk("whitening", "Teeth whitening costs $380."),
            chunk("parking", "Free parking behind the building."),
        ]
    )
    results = retriever.search("how much is whitening", 2)
    assert results[0].chunk.id == "whitening"
    assert len(results) == 1  # sections with no matching words are not returned


def test_search_with_no_useful_words_returns_nothing() -> None:
    retriever = BM25Retriever([chunk("hours", "We open at 8 am.")])
    assert retriever.search("what is it", 3) == []
    assert retriever.search("hours", 0) == []
