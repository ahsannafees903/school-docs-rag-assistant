from __future__ import annotations

import pytest

from app.providers.fake import HashingEmbedder, tokenize
from app.rag import RAGService


def test_fake_embedder_is_deterministic_and_normalised() -> None:
    emb = HashingEmbedder(dimension=64)
    a, b = emb.embed(["late fee policy"]), emb.embed(["late fee policy"])
    assert a == b
    assert abs(sum(v * v for v in a[0]) - 1.0) < 1e-6


def test_tokenize_drops_stopwords_and_stems() -> None:
    assert tokenize("What are the fees for exams?") == ["fee", "exam"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the late fee if tuition is paid after the 10th?", "fee_structure_2026-27.pdf"),
        ("What happens if a student is caught cheating?", "exam_rules.md"),
        ("When does the winter break start?", "holiday_calendar_2026-27.txt"),
        ("Which documents are required for admission?", "admission_policy.md"),
    ],
)
def test_top_hit_is_the_right_document(
    loaded_service: RAGService, question: str, expected: str
) -> None:
    hits = loaded_service.retrieve(question)
    assert hits[0].document_name == expected


def test_scores_are_sorted_and_top_k_respected(loaded_service: RAGService) -> None:
    hits = loaded_service.retrieve("exam rules", top_k=3)
    assert len(hits) == 3
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_pdf_hits_carry_page_numbers(loaded_service: RAGService) -> None:
    hits = loaded_service.retrieve("late fee charged after the 10th of the month")
    top = hits[0]
    assert top.document_name == "fee_structure_2026-27.pdf"
    assert top.page == 2


def test_empty_index_returns_nothing(service: RAGService) -> None:
    assert service.retrieve("anything") == []
