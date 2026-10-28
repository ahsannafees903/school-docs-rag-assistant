"""Persistence: SQLite for document/chunk metadata, FAISS for vectors.

Chunk row ids in SQLite are used as FAISS vector ids (``IndexIDMap2``), so a search hit
maps straight back to its text, document and page, and deleting a document removes
exactly its vectors.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from app.errors import AppError

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    pages INTEGER NOT NULL,
    chunks INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page INTEGER,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    filename: str
    content_type: str
    size_bytes: int
    pages: int
    chunks: int
    created_at: str


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    document_id: str
    document_name: str
    page: int | None
    text: str
    score: float


class VectorStore:
    """Thread-safe store combining a SQLite database and a FAISS inner-product index."""

    def __init__(self, data_dir: Path, dimension: int, embedder_name: str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "metadata.db"
        self.index_path = self.data_dir / "index.faiss"
        self.dimension = dimension
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        self._check_embedder(embedder_name)
        self.index = self._load_index()

    # ---- setup -----------------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _check_embedder(self, embedder_name: str) -> None:
        signature = f"{embedder_name}:{self.dimension}"
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'embedder'").fetchone()
            if row is None:
                conn.execute("INSERT INTO meta (key, value) VALUES ('embedder', ?)", (signature,))
            elif row["value"] != signature:
                raise AppError(
                    "INDEX_MISMATCH",
                    f"The index in '{self.data_dir}' was built with '{row['value']}' but the "
                    f"current provider is '{signature}'. Use a different DATA_DIR or delete it "
                    "and re-ingest.",
                    status_code=500,
                )

    def _load_index(self) -> faiss.IndexIDMap2:
        if self.index_path.exists():
            index = faiss.read_index(str(self.index_path))
            if index.d != self.dimension:
                raise AppError("INDEX_MISMATCH", "FAISS index dimension mismatch", 500)
            return index
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self.dimension))

    def _persist_index(self) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        faiss.write_index(self.index, str(tmp))
        tmp.replace(self.index_path)

    # ---- writes ----------------------------------------------------------------
    def add_document(
        self,
        record: DocumentRecord,
        chunks: list[tuple[int, int | None, str]],
        vectors: list[list[float]],
    ) -> None:
        """Insert a document with its ``(chunk_index, page, text)`` chunks and vectors."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        matrix = _normalize(np.asarray(vectors, dtype="float32"))
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.filename,
                    record.content_type,
                    record.size_bytes,
                    record.pages,
                    record.chunks,
                    record.created_at,
                ),
            )
            ids = []
            for chunk_index, page, text in chunks:
                cur = conn.execute(
                    "INSERT INTO chunks (document_id, chunk_index, page, text) VALUES (?, ?, ?, ?)",
                    (record.id, chunk_index, page, text),
                )
                ids.append(cur.lastrowid)
            self.index.add_with_ids(matrix, np.asarray(ids, dtype="int64"))
            self._persist_index()

    def delete_document(self, document_id: str) -> bool:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
            ).fetchall()
            deleted = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,)).rowcount
            if not deleted:
                return False
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            if rows:
                self.index.remove_ids(np.asarray([r["id"] for r in rows], dtype="int64"))
                self._persist_index()
            return True

    # ---- reads -----------------------------------------------------------------
    def list_documents(self) -> list[DocumentRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [DocumentRecord(**dict(r)) for r in rows]

    def get_document(self, document_id: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def find_by_filename(self, filename: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE filename = ? LIMIT 1", (filename,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    @property
    def vector_count(self) -> int:
        return int(self.index.ntotal)

    def search(self, vector: list[float], top_k: int) -> list[ChunkHit]:
        with self._lock:
            if self.index.ntotal == 0:
                return []
            query = _normalize(np.asarray([vector], dtype="float32"))
            scores, ids = self.index.search(query, min(top_k, int(self.index.ntotal)))
        pairs = [(int(i), float(s)) for i, s in zip(ids[0], scores[0], strict=True) if i != -1]
        if not pairs:
            return []
        placeholders = ",".join("?" for _ in pairs)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT c.id, c.document_id, c.page, c.text, d.filename FROM chunks c "
                f"JOIN documents d ON d.id = c.document_id WHERE c.id IN ({placeholders})",
                [i for i, _ in pairs],
            ).fetchall()
        by_id = {r["id"]: r for r in rows}
        hits = []
        for chunk_id, score in pairs:
            row = by_id.get(chunk_id)
            if row is not None:
                hits.append(
                    ChunkHit(
                        chunk_id,
                        row["document_id"],
                        row["filename"],
                        row["page"],
                        row["text"],
                        score,
                    )
                )
        return hits


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise rows so inner product == cosine similarity."""
    matrix = np.ascontiguousarray(matrix, dtype="float32")
    faiss.normalize_L2(matrix)
    return matrix
