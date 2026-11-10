# Changelog

## 1.1.0 — 2026-11-05

Portfolio cut of School Docs Assistant. The package version reported by `GET /health` is `1.1.0`. This pull request does not create the git tag.

### Added in this release

- README pipeline diagram: ingest → chunk → embed → FAISS → retrieve → threshold → LLM → citations.
- README **Design decisions**: refusal threshold, `IndexFlatIP`, one JSON envelope, local Ollama.
- [docs/demo.md](docs/demo.md) with the exact offline commands and the output of a real run, plus [docs/demo.gif](docs/demo.gif) of the chat UI on the fake provider.
- [docs/sessions/p1-s3.md](docs/sessions/p1-s3.md).
- `leetcode/contains-duplicate.py`.

### Already on main, listed here because there was no earlier changelog

- Local Ollama is the default (`llama3.2:3b`, `nomic-embed-text`). A normal run sends no paid API key.
- Optional hybrid retrieval (`RETRIEVAL_MODE=hybrid`) blends FAISS cosine with BM25. The default stays vector-only.
- Grounded answers with file and page citations, and a score threshold that refuses before the LLM.
- Offline `fake` provider for pytest, CI, and the retrieval eval.

### v1.1 checklist

- [x] Mermaid architecture diagram in the README
- [x] Design decisions section in the README
- [x] Demo a reviewer can run in under two minutes (`docs/demo.md`) and a GIF of that UI (`docs/demo.gif`)
- [x] Tests pass with the offline fake provider (`pytest -q`)
- [x] Release notes in this file
- [ ] Git tag `v1.1.0` (not created here; tag `main` after merge if you want it)
- [ ] Publish eval numbers for `nomic-embed-text` (Ollama was not running in this environment)
