"""The RAG pipeline: ingest documents, retrieve chunks, produce grounded answers."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from app.config import Settings
from app.errors import AppError
from app.ingestion import SUPPORTED_EXTENSIONS, chunk_pages, extract_pages, validate_filename
from app.models import ChatResponse, DocumentOut, Source
from app.prompts import NOT_FOUND_ANSWER
from app.providers import Providers, build_providers
from app.providers.base import ContextChunk
from app.store import ChunkHit, DocumentRecord, VectorStore

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 240


class RAGService:
    def __init__(self, settings: Settings, providers: Providers | None = None) -> None:
        self.settings = settings
        self.providers = providers or build_providers(settings)
        self.min_score = (
            settings.min_score
            if settings.min_score is not None
            else self.providers.default_min_score
        )
        self._store: VectorStore | None = None

    @property
    def store(self) -> VectorStore:
        # Created lazily so the app can boot (and /health can answer) before a model is up.
        if self._store is None:
            embedder = self.providers.embedder
            self._store = VectorStore(self.settings.data_dir, embedder.dimension, embedder.name)
        return self._store

    # ---- documents -------------------------------------------------------------
    def ingest(self, filename: str, content: bytes) -> DocumentOut:
        started = time.perf_counter()
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "document"
        ext = validate_filename(filename)
        if not content:
            raise AppError("EMPTY_DOCUMENT", f"'{filename}' is empty.", status_code=422)
        if len(content) > self.settings.max_upload_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"'{filename}' is larger than {self.settings.max_upload_mb:g} MB.",
                status_code=413,
            )

        pages = extract_pages(filename, content)
        chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        vectors = self.providers.embedder.embed([c.text for c in chunks])

        record = DocumentRecord(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            content_type=SUPPORTED_EXTENSIONS[ext],
            size_bytes=len(content),
            pages=len(pages),
            chunks=len(chunks),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self.store.add_document(record, [(c.index, c.page, c.text) for c in chunks], vectors)
        logger.info(
            "document_ingested",
            extra={
                "document_id": record.id,
                "doc_name": filename,
                "pages": record.pages,
                "chunks": record.chunks,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return DocumentOut(**record.__dict__)

    def list_documents(self) -> list[DocumentOut]:
        return [DocumentOut(**r.__dict__) for r in self.store.list_documents()]

    def delete_document(self, document_id: str) -> None:
        if not self.store.delete_document(document_id):
            raise AppError("NOT_FOUND", f"Document '{document_id}' not found.", status_code=404)
        logger.info("document_deleted", extra={"document_id": document_id})

    # ---- question answering ----------------------------------------------------
    def retrieve(self, question: str, top_k: int | None = None) -> list[ChunkHit]:
        query_vector = self.providers.embedder.embed([question])[0]
        return self.store.search(query_vector, top_k or self.settings.top_k)

    def answer(self, question: str, top_k: int | None = None) -> ChatResponse:
        started = time.perf_counter()
        hits = self.retrieve(question, top_k)
        relevant = [h for h in hits if h.score >= self.min_score]
        best = round(hits[0].score, 3) if hits else None

        if not relevant:
            logger.info("chat_refused", extra={"best_score": best, "min_score": self.min_score})
            return ChatResponse(answer=NOT_FOUND_ANSWER, grounded=False, sources=[])

        contexts = [
            ContextChunk(i + 1, h.document_name, h.page, h.text) for i, h in enumerate(relevant)
        ]
        answer = self.providers.chat.answer(question, contexts)
        grounded = answer.strip() != NOT_FOUND_ANSWER
        sources = [_to_source(h) for h in relevant] if grounded else []
        logger.info(
            "chat_answered",
            extra={
                "best_score": best,
                "sources": len(sources),
                "grounded": grounded,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return ChatResponse(answer=answer, grounded=grounded, sources=sources)


def _to_source(hit: ChunkHit) -> Source:
    snippet = " ".join(hit.text.split())
    if len(snippet) > SNIPPET_CHARS:
        snippet = snippet[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
    return Source(
        document_id=hit.document_id,
        document_name=hit.document_name,
        page=hit.page,
        snippet=snippet,
        score=round(hit.score, 4),
    )
