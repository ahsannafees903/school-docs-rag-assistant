"""Ingest every file in sample_docs/ (or a folder you pass) into the configured index.

Usage:
    python scripts/ingest_samples.py              # uses PROVIDER etc. from .env
    python scripts/ingest_samples.py my_docs/ --force
Files that are already in the index (same filename) are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.ingestion import SUPPORTED_EXTENSIONS  # noqa: E402
from app.rag import RAGService  # noqa: E402


def ingest_folder(service: RAGService, folder: Path, force: bool = False) -> list[str]:
    ingested = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.name.startswith("."):
            continue
        existing = service.store.find_by_filename(path.name)
        if existing and not force:
            print(f"skip   {path.name} (already indexed as {existing.id})")
            continue
        if existing and force:
            service.delete_document(existing.id)
        doc = service.ingest(path.name, path.read_bytes())
        print(f"added  {doc.filename}: {doc.pages} page(s), {doc.chunks} chunk(s) -> {doc.id}")
        ingested.append(doc.id)
    return ingested


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", default=str(ROOT / "sample_docs"))
    parser.add_argument("--force", action="store_true", help="re-ingest files already indexed")
    args = parser.parse_args()
    settings = Settings()
    service = RAGService(settings)
    print(f"provider={settings.provider} data_dir={settings.data_dir}")
    ingest_folder(service, Path(args.folder), force=args.force)


if __name__ == "__main__":
    main()
