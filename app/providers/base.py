"""Provider interfaces. Every embedding/chat backend implements these two classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextChunk:
    """A retrieved chunk handed to the LLM, numbered for citation as [n]."""

    number: int
    document_name: str
    page: int | None
    text: str


class EmbeddingProvider(ABC):
    """Turns text into fixed-size vectors."""

    name: str = "base"

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatProvider(ABC):
    """Writes an answer to a question using only the supplied context."""

    name: str = "base"

    @abstractmethod
    def answer(self, question: str, contexts: list[ContextChunk]) -> str: ...


@dataclass(frozen=True)
class Providers:
    embedder: EmbeddingProvider
    chat: ChatProvider
    default_min_score: float
