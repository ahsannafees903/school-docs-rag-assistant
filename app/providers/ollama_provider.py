"""Local models through Ollama (https://ollama.com): llama3 + nomic-embed-text by default."""

from __future__ import annotations

import httpx

from app.errors import ProviderError
from app.prompts import build_messages
from app.providers.base import ChatProvider, ContextChunk, EmbeddingProvider


class _OllamaClient:
    def __init__(
        self, base_url: str, timeout: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        )

    def post(self, path: str, payload: dict) -> dict:
        try:
            resp = self._client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Ollama returned {exc.response.status_code}: {exc.response.text[:200]}. "
                f"Did you run `ollama pull {payload.get('model')}`?"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Could not reach Ollama: {exc}. Is `ollama serve` running?"
            ) from exc


class OllamaEmbedder(EmbeddingProvider):
    name = "ollama"

    def __init__(self, client: _OllamaClient, model: str) -> None:
        self._client = client
        self.model = model
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed(["dimension probe"])[0])
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        data = self._client.post("/api/embed", {"model": self.model, "input": texts})
        try:
            return data["embeddings"]
        except KeyError as exc:
            raise ProviderError("Unexpected response shape from Ollama /api/embed") from exc


class OllamaChat(ChatProvider):
    name = "ollama"

    def __init__(self, client: _OllamaClient, model: str) -> None:
        self._client = client
        self.model = model

    def answer(self, question: str, contexts: list[ContextChunk]) -> str:
        data = self._client.post(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": build_messages(question, contexts),
            },
        )
        try:
            return data["message"]["content"].strip()
        except (KeyError, AttributeError) as exc:
            raise ProviderError("Unexpected response shape from Ollama /api/chat") from exc


def build_ollama(
    base_url: str, chat_model: str, embed_model: str, timeout: float
) -> tuple[OllamaEmbedder, OllamaChat]:
    client = _OllamaClient(base_url, timeout)
    return OllamaEmbedder(client, embed_model), OllamaChat(client, chat_model)
