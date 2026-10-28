"""Provider factory: picks the embedding + chat backend from settings."""

from __future__ import annotations

from app.config import Settings
from app.providers.base import ChatProvider, ContextChunk, EmbeddingProvider, Providers

# Starting points for MIN_SCORE (cosine similarity). The fake value is tuned with
# scripts/eval.py on sample_docs; the others are untuned defaults. Measure on your data.
DEFAULT_MIN_SCORES = {"fake": 0.15, "openai": 0.30, "ollama": 0.45}


def build_providers(settings: Settings) -> Providers:
    if settings.provider == "fake":
        from app.providers.fake import ExtractiveChat, HashingEmbedder

        embedder, chat = HashingEmbedder(), ExtractiveChat()
    elif settings.provider == "openai":
        from app.providers.openai_provider import build_openai

        embedder, chat = build_openai(
            settings.openai_api_key,
            settings.openai_base_url,
            settings.openai_chat_model,
            settings.openai_embed_model,
            settings.request_timeout_s,
        )
    elif settings.provider == "ollama":
        from app.providers.ollama_provider import build_ollama

        embedder, chat = build_ollama(
            settings.ollama_base_url,
            settings.ollama_chat_model,
            settings.ollama_embed_model,
            settings.request_timeout_s,
        )
    else:  # pragma: no cover - guarded by the Literal type in Settings
        raise ValueError(f"Unknown provider: {settings.provider}")
    return Providers(embedder, chat, DEFAULT_MIN_SCORES[settings.provider])


__all__ = [
    "ChatProvider",
    "ContextChunk",
    "DEFAULT_MIN_SCORES",
    "EmbeddingProvider",
    "Providers",
    "build_providers",
]
