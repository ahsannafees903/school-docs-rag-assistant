"""Real providers, tested against mocked HTTP so no network or API key is needed."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.config import Settings
from app.errors import ProviderError
from app.prompts import SYSTEM_PROMPT
from app.providers import build_providers
from app.providers.base import ContextChunk
from app.providers.ollama_provider import OllamaChat, OllamaEmbedder, _OllamaClient
from app.providers.openai_provider import OpenAIChat, OpenAIEmbedder, _OpenAIClient

CTX = [ContextChunk(1, "fees.pdf", 2, "The late fee is 500 PKR.")]


def mock(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_ollama_embed_and_chat() -> None:
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]] * len(body["input"])})
        return httpx.Response(200, json={"message": {"content": " 500 PKR [1] "}})

    client = _OllamaClient("http://ollama:11434", 5, transport=mock(handler))
    embedder = OllamaEmbedder(client, "nomic-embed-text")
    assert embedder.dimension == 3
    assert embedder.embed(["a", "b"]) == [[0.1, 0.2, 0.3]] * 2
    assert OllamaChat(client, "llama3").answer("late fee?", CTX) == "500 PKR [1]"

    path, chat_body = seen[-1]
    assert path == "/api/chat"
    assert chat_body["model"] == "llama3"
    assert chat_body["stream"] is False
    assert chat_body["messages"][0]["content"] == SYSTEM_PROMPT


def test_ollama_missing_model_is_provider_error() -> None:
    client = _OllamaClient(
        "http://ollama:11434", 5, transport=mock(lambda r: httpx.Response(404, text="not found"))
    )
    with pytest.raises(ProviderError, match="ollama pull nomic-embed-text"):
        OllamaEmbedder(client, "nomic-embed-text").embed(["x"])


def test_openai_embed_and_chat() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk-test"
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            data = [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
            return httpx.Response(200, json={"data": list(reversed(data))})
        assert body["temperature"] == 0
        return httpx.Response(200, json={"choices": [{"message": {"content": "500 PKR [1]"}}]})

    client = _OpenAIClient("sk-test", "https://api.openai.com/v1", 5, transport=mock(handler))
    embedder = OpenAIEmbedder(client, "text-embedding-3-small")
    assert embedder.dimension == 1536
    assert embedder.embed(["a", "b"]) == [[0.0, 1.0], [1.0, 1.0]]  # re-ordered by index
    assert OpenAIChat(client, "gpt-4o-mini").answer("late fee?", CTX) == "500 PKR [1]"


def test_openai_auth_error_is_provider_error() -> None:
    client = _OpenAIClient(
        "sk-bad",
        "https://api.openai.com/v1",
        5,
        transport=mock(lambda r: httpx.Response(401, json={"error": "bad key"})),
    )
    with pytest.raises(ProviderError, match="401"):
        OpenAIChat(client, "gpt-4o-mini").answer("q", CTX)


def test_openai_requires_key() -> None:
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        build_providers(Settings(_env_file=None, provider="openai", openai_api_key=""))


@pytest.mark.parametrize(("name", "threshold"), [("fake", 0.15), ("ollama", 0.45)])
def test_factory_picks_provider(name: str, threshold: float) -> None:
    providers = build_providers(Settings(_env_file=None, provider=name))
    assert providers.embedder.name == name
    assert providers.chat.name == name
    assert providers.default_min_score == threshold
