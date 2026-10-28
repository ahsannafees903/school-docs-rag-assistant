# Design decisions

Short records of *why* things are the way they are. Numbers below were measured with
`python scripts/eval.py` on the 4 sample documents and 24 eval questions using the
**fake** (lexical) provider; they are a sanity check, not a benchmark.

## 1. FAISS (flat inner-product) instead of a vector database
- **Context:** a school has tens to hundreds of documents, i.e. thousands of chunks.
- **Decision:** `faiss.IndexIDMap2(IndexFlatIP)` persisted to `data/index.faiss`, with
  metadata in SQLite.
- **Why:** exact search over a few thousand vectors takes milliseconds, so approximate
  indexes (IVF/HNSW) add tuning without benefit. FAISS is a single pip dependency with no
  server to run, and `IndexIDMap2` lets us use SQLite chunk ids as vector ids, which makes
  delete-by-document exact.
- **Trade-off / when to change:** no metadata filtering inside the index and a single
  process owns the file. Past ~1M chunks or multi-instance deployment, move to pgvector,
  Qdrant or similar behind the same `VectorStore` interface.

## 2. Cosine similarity via normalised inner product
Vectors are L2-normalised before insert and search, so the inner product **is** cosine
similarity in [-1, 1]. That makes `MIN_SCORE` meaningful and comparable across documents.

## 3. Chunk size 400 characters, overlap 80
- School policies are short, self-contained rules ("late fee is 500 PKR after the 10th").
  Small chunks keep one rule per chunk, so citations point at the exact rule and the
  snippet a parent sees is readable.
- Overlap (20%) keeps a sentence that straddles a boundary retrievable from either side.
- Boundaries snap to paragraph → line → sentence → word, so words are never split.
- Measured on the sample set (fake provider; for each size, the lowest threshold that
  refuses all 4 out-of-scope questions):
  | chunk/overlap | min_score | hit@1 | refusal |
  |---|---|---|---|
  | 800/150 | 0.20 | 85% | 100% |
  | 600/120 | 0.20 | 75% | 100% |
  | 500/100 | 0.20 | 90% | 100% |
  | 400/80  | 0.15 | 95% | 100% |
- Longer documents with richer embeddings may prefer 800-1200; both values are settings.

## 4. A retrieval score threshold before the LLM
- **Decision:** if the best chunk's cosine score is below `MIN_SCORE`, return a fixed
  "I couldn't find the answer…" response and do not call the LLM.
- **Why:** the most damaging failure for a school assistant is a confident wrong answer
  about fees or dates. Refusing early is cheap, deterministic and testable. The system
  prompt is a second line of defence ("use ONLY the context… otherwise reply exactly…").
- **Value:** the threshold depends on the embedding model, so each provider has a default
  (`fake=0.15`, `openai=0.30`, `ollama=0.45`) and `MIN_SCORE` overrides it. Only the fake
  value is measured here: at 0.15 it gives hit@1 95% and refuses all 4 out-of-scope
  questions; at 0.10 refusal drops to 75%; at 0.20 hit@1 drops to 85%. The OpenAI/Ollama
  defaults are starting points: run `python scripts/eval.py --sweep` with your provider
  and pick the value where answerable hits stay high and refusals reach 100%.

## 5. Provider abstraction (`EmbeddingProvider` + `ChatProvider`)
- Two tiny ABCs: `embed(texts) -> vectors` and `answer(question, contexts) -> str`.
- **Why:** the pipeline should not care whether vectors come from OpenAI, a local Ollama
  model, or a test double. Switching is one env var (`PROVIDER`), and adding e.g. Gemini
  or a sentence-transformers model is one new file.
- Real providers call the REST APIs directly with `httpx` (no vendor SDKs), which keeps
  dependencies small and makes error handling uniform (`ProviderError` → `502`).
- **Fake provider:** a hashing bag-of-words embedder plus an extractive "LLM" that only
  quotes sentences from the retrieved context. It is deterministic and offline, so the
  whole test suite and CI run with no keys, no network and no GPU. It is lexical, not
  semantic: it cannot match "Grade 7" to "Grade 6 to Grade 8", for example.

## 6. One JSON envelope for every response
See [API_STANDARDS.md](API_STANDARDS.md). A "works on my machine" endpoint that returns a
different shape on errors breaks every client that parses it, so the envelope is enforced
centrally by exception handlers and checked by tests for each error path.

## 7. SQLite for metadata
Zero-config, transactional, ships with Python, and fits the single-instance deployment.
Foreign keys + `ON DELETE CASCADE` keep chunks consistent with documents.

## 8. No build step for the UI
Plain HTML/CSS/JS served by FastAPI keeps the project runnable with `pip install` alone and
easy to read in a portfolio review. A framework would add tooling without adding value at
this size.
