from __future__ import annotations

import pytest
from simple_pdf import build_pdf

from app.errors import AppError
from app.ingestion import extract_pages
from app.rag import RAGService


def test_extract_pdf_pages() -> None:
    pdf = build_pdf([["Page one text about fees."], ["Page two text about exams."]])
    pages = extract_pages("doc.pdf", pdf)
    assert [p.number for p in pages] == [1, 2]
    assert "fees" in pages[0].text
    assert "exams" in pages[1].text


def test_extract_markdown_is_single_page() -> None:
    pages = extract_pages("notes.md", b"# Title\n\nSome content.")
    assert len(pages) == 1
    assert pages[0].number is None


def test_unsupported_extension() -> None:
    with pytest.raises(AppError) as err:
        extract_pages("virus.exe", b"MZ")
    assert err.value.code == "UNSUPPORTED_FILE_TYPE"
    assert err.value.status_code == 415


def test_empty_text_document() -> None:
    with pytest.raises(AppError) as err:
        extract_pages("blank.txt", b"   \n  ")
    assert err.value.code == "EMPTY_DOCUMENT"


def test_corrupt_pdf() -> None:
    with pytest.raises(AppError) as err:
        extract_pages("broken.pdf", b"%PDF-1.4 this is not really a pdf")
    assert err.value.code in {"INVALID_DOCUMENT", "EMPTY_DOCUMENT"}


def test_ingest_persists_metadata_and_vectors(service: RAGService) -> None:
    pdf = build_pdf([["Tuition is due by the 10th of every month."], ["Late fee is 500 PKR."]])
    doc = service.ingest("fees.pdf", pdf)
    assert doc.pages == 2
    assert doc.chunks == 2
    assert service.store.vector_count == 2
    assert (service.settings.data_dir / "index.faiss").exists()
    assert (service.settings.data_dir / "metadata.db").exists()


def test_index_survives_restart(service: RAGService) -> None:
    service.ingest("rules.txt", b"Mobile phones are not allowed in the examination hall.")
    reopened = RAGService(service.settings)
    assert reopened.store.vector_count == 1
    hits = reopened.retrieve("are mobile phones allowed in the exam hall?")
    assert hits[0].document_name == "rules.txt"


def test_delete_removes_vectors(service: RAGService) -> None:
    a = service.ingest("a.txt", b"Winter break starts on 21 December.")
    service.ingest("b.txt", b"The late fee is 500 PKR.")
    service.delete_document(a.id)
    assert service.store.vector_count == 1
    assert all(h.document_name == "b.txt" for h in service.retrieve("winter break"))


def test_delete_unknown_document(service: RAGService) -> None:
    with pytest.raises(AppError) as err:
        service.delete_document("nope")
    assert err.value.code == "NOT_FOUND"


def test_file_too_large(service: RAGService) -> None:
    service.settings.max_upload_mb = 0.001
    with pytest.raises(AppError) as err:
        service.ingest("big.txt", b"x " * 2000)
    assert err.value.code == "FILE_TOO_LARGE"
