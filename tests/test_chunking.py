from __future__ import annotations

import pytest

from app.ingestion import Page, chunk_pages, chunk_text, normalize_text


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Fees are due on the 10th.", size=100, overlap=10) == [
        "Fees are due on the 10th."
    ]


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("   \n ", size=100, overlap=10) == []


def test_chunks_respect_size_and_cover_all_words() -> None:
    words = [f"word{i}" for i in range(400)]
    text = " ".join(words)
    chunks = chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    seen = set(" ".join(chunks).split())
    assert seen == set(words)


def test_consecutive_chunks_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(300))
    chunks = chunk_text(text, size=120, overlap=30)
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.split()[-1] in right.split()[:12]


def test_chunks_never_split_words() -> None:
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 20
    vocab = set(text.split())
    for chunk in chunk_text(text, size=57, overlap=11):
        assert set(chunk.split()) <= vocab


def test_prefers_paragraph_breaks() -> None:
    para1 = "First paragraph sentence. " * 5
    text = para1.strip() + "\n\n" + "Second paragraph here. " * 5
    chunks = chunk_text(text, size=len(para1) + 20, overlap=10)
    assert chunks[0].endswith("sentence.")


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_parameters(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("some text", size=size, overlap=overlap)


def test_chunk_pages_keeps_page_numbers_and_global_index() -> None:
    pages = [Page(1, "a " * 150), Page(2, "b " * 150)]
    chunks = chunk_pages(pages, size=120, overlap=20)
    assert {c.page for c in chunks} == {1, 2}
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_normalize_text() -> None:
    assert normalize_text("a  \t b\r\n\n\n\nc ") == "a b\n\nc"
