"""Pydantic schemas for request and response payloads (the ``data`` part of the envelope)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    pages: int
    chunks: int
    created_at: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class Source(BaseModel):
    document_id: str
    document_name: str
    page: int | None
    snippet: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[Source]
