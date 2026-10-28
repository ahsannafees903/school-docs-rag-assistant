from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rag import RAGService

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS = ROOT / "sample_docs"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: tests never read a developer's local .env
    return Settings(
        _env_file=None, provider="fake", data_dir=tmp_path / "data", log_level="WARNING"
    )


@pytest.fixture
def service(settings: Settings) -> RAGService:
    return RAGService(settings)


@pytest.fixture
def loaded_service(service: RAGService) -> RAGService:
    for path in sorted(SAMPLE_DOCS.iterdir()):
        service.ingest(path.name, path.read_bytes())
    return service


@pytest.fixture
def client(settings: Settings, service: RAGService) -> TestClient:
    return TestClient(create_app(settings, service))
