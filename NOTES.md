# How a question becomes an answer

A parent types a question.
FAISS finds the closest chunks of the school documents.
If the best score is below the threshold the assistant refuses; otherwise Llama 3 answers with citations.

## Pipeline

### 1. Ingest

Upload a PDF, TXT or Markdown file. Text is extracted one page at a time (a TXT or Markdown file is a single page).

**Why:** the assistant can only quote words that were actually pulled out of the file.

### 2. Chunk

Each page is split into pieces of about 400 characters, with 80 characters of overlap, breaking on a paragraph, sentence or word.

**Why:** a short chunk is usually one rule, so the citation points at that rule instead of a whole chapter.

### 3. Embed

Each chunk is turned into a vector (a list of numbers) by `nomic-embed-text` running locally in Ollama.

**Why:** similar meanings land near each other, so a question can match a passage even when the words are not identical.

### 4. FAISS

Those vectors go into a FAISS index on disk. The original text, file name and page number go into SQLite.

**Why:** FAISS finds the nearest vectors, and SQLite is what we show back as the file and page.

### 5. Retrieve

The question is embedded with the same model, then FAISS returns the closest chunks (4 by default), scored by cosine similarity.

**Why:** the language model should see only the passages that might contain the answer, not every document.

### 6. Refusal threshold

If the best chunk scores below `MIN_SCORE` (0.45 for Ollama, unless you set it), the app returns a fixed "not in the documents" message and does not call the LLM.

**Why:** a made-up fee or date is worse than saying "I don't know", and skipping the model makes that decision easy to test.

### 7. LLM

Chunks that pass the threshold are numbered and sent to the local chat model `llama3.2:3b` (use `llama3.1:8b` on a 16 GB RAM machine) with a prompt that says: use only this context.

**Why:** the model writes a normal sentence, but it is not allowed to invent facts from outside the retrieved text.

### 8. Citations

The answer includes bracket numbers such as `[1]`, and the API returns each source's document name, page, snippet and score.

**Why:** a parent can open the file and check the sentence the answer came from.

## What tests use

Pytest and CI set `PROVIDER=fake`. That path uses a tiny offline embedder and an extractive "answer" that only quotes the retrieved text. It never starts Ollama and never calls a paid API.
