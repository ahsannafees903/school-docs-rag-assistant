"""OpenAI embeddings + chat via the REST API (no SDK dependency)."""

from __future__ import annotations

import httpx

from app.errors import ProviderError
from app.prompts import build_messages
from app.providers.base import ChatProvider, ContextChunk, EmbeddingProvider

_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class _OpenAIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set. Add it to .env or use PROVIDER=ollama.")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def post(self, path: str, payload: dict) -> dict:
        try:
            resp = self._client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"OpenAI returned {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach OpenAI: {exc}") from exc


class OpenAIEmbedder(EmbeddingProvider):
    name = "openai"

    def __init__(self, client: _OpenAIClient, model: str) -> None:
        self._client = client
        self.model = model
        self._dim = _DIMENSIONS.get(model)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed(["dimension probe"])[0])
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 96):
            data = self._client.post(
                "/embeddings", {"model": self.model, "input": texts[i : i + 96]}
            )
            vectors.extend(
                item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])
            )
        return vectors


class OpenAIChat(ChatProvider):
    name = "openai"

    def __init__(self, client: _OpenAIClient, model: str) -> None:
        self._client = client
        self.model = model

    def answer(self, question: str, contexts: list[ContextChunk]) -> str:
        data = self._client.post(
            "/chat/completions",
            {"model": self.model, "temperature": 0, "messages": build_messages(question, contexts)},
        )
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise ProviderError("Unexpected response shape from OpenAI chat API") from exc


def build_openai(
    api_key: str, base_url: str, chat_model: str, embed_model: str, timeout: float
) -> tuple[OpenAIEmbedder, OpenAIChat]:
    client = _OpenAIClient(api_key, base_url, timeout)
    return OpenAIEmbedder(client, embed_model), OpenAIChat(client, chat_model)
