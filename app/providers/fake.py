"""Deterministic, offline providers for tests, CI and demos.

* ``HashingEmbedder``: a bag-of-words "hashing trick" embedding. Lexical, not semantic,
  but stable and good enough to exercise the full retrieval pipeline without a model.
* ``ExtractiveChat``: answers by quoting the context sentence(s) that best overlap the
  question. It can only ever return text that is already in the documents.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.prompts import NOT_FOUND_ANSWER
from app.providers.base import ChatProvider, ContextChunk, EmbeddingProvider

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "my",
        "we",
        "me",
        "any",
        "much",
        "many",
        "should",
        "would",
        "could",
        "about",
        "into",
        "than",
        "then",
        "them",
        "they",
    }
)


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in _STOPWORDS:
            continue
        # Tiny stemmer so "fees"/"fee" and "exams"/"exam" match.
        if len(tok) > 4 and tok.endswith("ies"):
            tok = tok[:-3] + "y"
        elif len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


class HashingEmbedder(EmbeddingProvider):
    name = "fake"

    def __init__(self, dimension: int = 512) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.md5(token.encode(), usedforsecurity=False).digest()
        index = int.from_bytes(digest[:4], "little") % self._dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        return index, sign

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self._dim
            for tok in tokenize(text):
                idx, sign = self._bucket(tok)
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class ExtractiveChat(ChatProvider):
    name = "fake"

    def __init__(self, max_sentences: int = 2) -> None:
        self.max_sentences = max_sentences

    def answer(self, question: str, contexts: list[ContextChunk]) -> str:
        q_tokens = set(tokenize(question))
        scored: list[tuple[float, int, str]] = []
        seen: set[str] = set()
        for ctx in contexts:
            for sentence in _sentences(ctx.text):
                s_tokens = set(tokenize(sentence))
                complete = sentence.endswith((".", "!", "?", ")"))
                if len(s_tokens) < 3 or (not complete and len(s_tokens) < 6):
                    continue  # skip headings and short fragments cut at a chunk boundary
                if sentence in seen:
                    continue  # overlapping chunks repeat sentences
                seen.add(sentence)
                overlap = len(q_tokens & s_tokens)
                if overlap:
                    scored.append((overlap / math.sqrt(len(s_tokens)), ctx.number, sentence))
        if not scored:
            return NOT_FOUND_ANSWER
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][0]
        # Keep runner-up sentences only if they are nearly as relevant as the best one.
        picked = [item for item in scored[: self.max_sentences] if item[0] >= 0.75 * best]
        return " ".join(f"{sentence} [{number}]" for _, number, sentence in picked)


def _sentences(text: str) -> list[str]:
    """Split a chunk into sentences.

    Hard-wrapped lines are re-joined into paragraphs first, headings stand alone, and a
    line ending in ':' keeps the bullet list that follows it as one "sentence".
    """
    blocks: list[str] = []
    current: list[str] = []
    is_list = False

    def flush() -> None:
        nonlocal current, is_list
        if current:
            blocks.append(("; " if is_list else " ").join(current))
        current, is_list = [], False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("#"):
            flush()
            blocks.append(line.strip("# "))
        elif line.startswith(("-", "*")):
            item = line.lstrip("-* ").rstrip(".")
            if current and (is_list or current[-1].endswith(":")):
                if not is_list:
                    current, is_list = [" ".join(current) + " " + item], True
                else:
                    current.append(item)
            else:
                flush()
                blocks.append(item)
        elif not current and len(line.split()) <= 5 and not line.endswith((".", ":", ")")):
            blocks.append(line)  # a short unpunctuated line on its own is a heading
        else:
            if is_list:
                flush()
            current.append(line)
    flush()

    out: list[str] = []
    for block in blocks:
        out.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", block) if part.strip())
    return out
