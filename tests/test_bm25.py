"""BM25 keyword scores and the weighted blend with vector scores."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.bm25 import BM25Index, fuse_scores
from app.config import Settings
from app.rag import RAGService

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS = ROOT / "sample_docs"


def test_bm25_ranks_the_chunk_that_contains_the_words() -> None:
    index = BM25Index()
    index.add_corpus(
        [
            (1, "the school bus route is posted at the gate"),
            (2, "a late fee of 500 PKR is charged after the 10th"),
            (3, "winter break starts in December"),
        ]
    )
    scores = index.score("late fee charged")
    assert scores[2] > scores.get(1, 0.0)
    assert scores[2] > scores.get(3, 0.0)


def test_rare_term_has_higher_idf_than_a_term_in_every_chunk() -> None:
    index = BM25Index()
    index.add_corpus(
        [
            (1, "zebra policy"),
            (2, "school policy"),
            (3, "school calendar"),
        ]
    )
    assert index.idf["zebra"] > index.idf["school"]


def test_shorter_chunk_wins_when_the_word_appears_once() -> None:
    index = BM25Index()
    index.add_corpus(
        [
            (1, "fee"),
            (2, "fee " + " filler" * 40),
            (3, "unrelated calendar dates holidays sports"),
        ]
    )
    scores = index.score("fee")
    assert scores[1] > scores[2]
    assert 3 not in scores


def test_stemming_matches_fee_and_fees() -> None:
    index = BM25Index()
    index.add_corpus([(1, "fee schedule"), (2, "holiday calendar")])
    assert index.score("fees")[1] > 0.0


def test_empty_corpus_and_stopword_query_score_nothing() -> None:
    index = BM25Index()
    index.add_corpus([])
    assert index.score("fee") == {}
    index.add_corpus([(1, "the late fee is 500")])
    assert index.score("what is the") == {}


def test_repeated_query_term_scores_higher() -> None:
    index = BM25Index()
    index.add_corpus([(1, "alpha beta"), (2, "gamma delta")])
    once = index.score("alpha")[1]
    twice = index.score("alpha alpha")[1]
    assert twice > once


def test_weight_one_ignores_bm25_and_clamps_negative_cosine() -> None:
    fused = fuse_scores({1: 0.2, 2: 0.9, 3: -0.4}, {1: 10.0, 3: 1.0}, vector_weight=1.0)
    assert [chunk_id for chunk_id, _ in fused] == [2, 1, 3]
    assert fused[0] == (2, pytest.approx(0.9))
    assert fused[-1][1] == pytest.approx(0.0)


def test_weight_zero_follows_max_normalised_bm25() -> None:
    fused = fuse_scores({1: 0.9}, {1: 0.0, 2: 5.0, 3: 10.0}, vector_weight=0.0)
    by_id = dict(fused)
    assert by_id[3] == pytest.approx(1.0)
    assert by_id[2] == pytest.approx(0.5)
    assert by_id[1] == pytest.approx(0.0)
    assert [chunk_id for chunk_id, _ in fused] == [3, 2, 1]


def test_equal_weight_blends_both_sides() -> None:
    fused = dict(fuse_scores({1: 1.0}, {2: 4.0}, vector_weight=0.5))
    assert fused[1] == pytest.approx(0.5)
    assert fused[2] == pytest.approx(0.5)


def test_ties_break_by_chunk_id() -> None:
    fused = fuse_scores({2: 0.5, 1: 0.5}, {}, vector_weight=1.0)
    assert [chunk_id for chunk_id, _ in fused] == [1, 2]


def test_empty_inputs_and_bad_weight() -> None:
    assert fuse_scores({}, {}, 0.5) == []
    with pytest.raises(ValueError, match="vector_weight"):
        fuse_scores({1: 1.0}, {}, 1.5)


def test_default_retrieval_mode_is_vector() -> None:
    settings = Settings(_env_file=None, provider="fake")
    assert settings.retrieval_mode == "vector"
    assert settings.hybrid_vector_weight == 0.5


def _loaded(tmp_path: Path, **overrides: object) -> RAGService:
    settings = Settings(
        _env_file=None,
        provider="fake",
        data_dir=tmp_path / "data",
        log_level="WARNING",
        **overrides,
    )
    service = RAGService(settings)
    for path in sorted(SAMPLE_DOCS.iterdir()):
        service.ingest(path.name, path.read_bytes())
    return service


def test_hybrid_mode_still_returns_the_late_fee_document(tmp_path: Path) -> None:
    service = _loaded(tmp_path, retrieval_mode="hybrid")
    hits = service.retrieve("What is the late fee if tuition is paid after the 10th?")
    assert hits[0].document_name == "fee_structure_2026-27.pdf"
    assert hits[0].page == 2
    assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)


def test_hybrid_weight_one_matches_vector_ranking(tmp_path: Path) -> None:
    question = "What happens if a student is caught cheating?"
    vector_hits = _loaded(tmp_path / "vector", retrieval_mode="vector").retrieve(question)
    hybrid_hits = _loaded(
        tmp_path / "hybrid", retrieval_mode="hybrid", hybrid_vector_weight=1.0
    ).retrieve(question)
    assert [hit.chunk_id for hit in hybrid_hits] == [hit.chunk_id for hit in vector_hits]
    assert [hit.score for hit in hybrid_hits] == pytest.approx([hit.score for hit in vector_hits])
