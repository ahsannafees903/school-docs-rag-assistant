"""Application settings, loaded from environment variables or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["fake", "ollama", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    provider: ProviderName = "fake"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_base_url: str = "https://api.openai.com/v1"

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3"
    ollama_embed_model: str = "nomic-embed-text"

    data_dir: Path = Path("data")

    chunk_size: int = Field(default=400, ge=100, le=8000)
    chunk_overlap: int = Field(default=80, ge=0)
    top_k: int = Field(default=4, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)

    max_upload_mb: float = Field(default=10, gt=0)
    request_timeout_s: float = Field(default=120, gt=0)
    log_level: str = "INFO"

    @field_validator("min_score", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_smaller_than_chunk(cls, value: int, info: ValidationInfo) -> int:
        size = info.data.get("chunk_size", 400)
        if value >= size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
