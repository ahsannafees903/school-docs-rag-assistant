"""Text extraction (PDF/TXT/MD) and overlapping chunking."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import AppError

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


@dataclass(frozen=True)
class Page:
    """Text of one page. ``number`` is 1-based for PDFs and ``None`` for plain text."""

    number: int | None
    text: str


@dataclass(frozen=True)
class Chunk:
    page: int | None
    index: int
    text: str


def file_extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def validate_filename(filename: str) -> str:
    ext = file_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise AppError(
            "UNSUPPORTED_FILE_TYPE",
            f"'{filename}' is not supported. Allowed types: {allowed}.",
            status_code=415,
        )
    return ext


def extract_pages(filename: str, content: bytes) -> list[Page]:
    """Extract text per page. Plain-text files are returned as a single page."""
    ext = validate_filename(filename)
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [Page(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
        except (PdfReadError, ValueError, KeyError) as exc:
            raise AppError("INVALID_DOCUMENT", f"Could not read PDF '{filename}': {exc}") from exc
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        pages = [Page(None, text)]

    pages = [Page(p.number, normalize_text(p.text)) for p in pages]
    if not any(p.text for p in pages):
        raise AppError(
            "EMPTY_DOCUMENT",
            f"No extractable text found in '{filename}'. Scanned PDFs need OCR first.",
            status_code=422,
        )
    return pages


def normalize_text(text: str) -> str:
    """Collapse runs of spaces/tabs and excess blank lines, keep paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split ``text`` into chunks of at most ``size`` characters with ``overlap``.

    Chunk boundaries snap to whitespace so words are never cut in half, preferring a
    paragraph or sentence break in the second half of the window when one exists.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and smaller than size")

    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            end = _best_break(text, start, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        next_start = max(end - overlap, start + 1)
        # Move forward to the start of a word so the overlap does not begin mid-word.
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return chunks


def _best_break(text: str, start: int, end: int) -> int:
    window_floor = start + (end - start) // 2
    for sep in ("\n\n", "\n", ". ", " "):
        pos = text.rfind(sep, window_floor, end)
        if pos != -1:
            return pos + len(sep)
    return end


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for piece in chunk_text(page.text, size, overlap):
            chunks.append(Chunk(page=page.number, index=len(chunks), text=piece))
    return chunks
