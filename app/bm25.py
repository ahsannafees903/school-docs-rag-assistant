"""BM25 keyword scores and the blend with FAISS cosine scores.

BM25 looks for the words in the question. A vector score looks for a similar
meaning. Hybrid mode adds the two, after putting them on the same 0–1 scale.

The blend is a weighted sum, not reciprocal rank fusion. Fusion scores are
about 1/60, so the existing ``MIN_SCORE`` gate (0.15 or 0.45) would refuse
every question. A weighted sum stays in ``[0, 1]``, so that gate still means
"not close enough".
"""

from __future__ import annotations

import math

from app.providers.fake import tokenize

# Okapi BM25 defaults. k1 controls how fast extra repetitions of a word stop
# helping. b controls how much a long chunk is penalised.
_DEFAULT_K1 = 1.5
_DEFAULT_B = 0.75


class BM25Index:
    """Okapi BM25 over ``(chunk_id, text)`` pairs.

    IDF uses the Lucene form ``log(1 + (N - df + 0.5) / (df + 0.5))``, so a
    word that appears in every chunk scores low but never negative.
    Tokens go through the same stemmer as the offline embedder (``fees`` and
    ``fee`` match).
    """

    def __init__(self, k1: float = _DEFAULT_K1, b: float = _DEFAULT_B) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[int] = []
        self.doc_lens: list[int] = []
        self.tfs: list[dict[str, int]] = []
        self.idf: dict[str, float] = {}
        self.n_docs = 0
        self.avgdl = 0.0

    def add_corpus(self, documents: list[tuple[int, str]]) -> None:
        """Index ``documents`` from scratch, replacing any previous corpus."""
        self.doc_ids = []
        self.doc_lens = []
        self.tfs = []
        doc_freq: dict[str, int] = {}
        total_len = 0
        for doc_id, text in documents:
            counts: dict[str, int] = {}
            for token in tokenize(text):
                counts[token] = counts.get(token, 0) + 1
            length = sum(counts.values())
            self.doc_ids.append(doc_id)
            self.doc_lens.append(length)
            self.tfs.append(counts)
            total_len += length
            for token in counts:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        self.n_docs = len(documents)
        self.avgdl = (total_len / self.n_docs) if self.n_docs else 0.0
        self.idf = {
            token: math.log(1.0 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for token, freq in doc_freq.items()
        }

    def score(self, query: str) -> dict[int, float]:
        """BM25 for each chunk that shares a query term. Missing ids score 0."""
        if self.n_docs == 0 or self.avgdl == 0.0:
            return {}
        tokens = tokenize(query)
        if not tokens:
            return {}
        totals = [0.0] * self.n_docs
        for token in tokens:
            idf = self.idf.get(token)
            if idf is None:
                continue
            for index, counts in enumerate(self.tfs):
                tf = counts.get(token, 0)
                if tf == 0:
                    continue
                length_norm = 1.0 - self.b + self.b * self.doc_lens[index] / self.avgdl
                denom = tf + self.k1 * length_norm
                totals[index] += idf * (tf * (self.k1 + 1.0)) / denom
        return {self.doc_ids[index]: total for index, total in enumerate(totals) if total > 0.0}


def fuse_scores(
    vector_scores: dict[int, float],
    bm25_scores: dict[int, float],
    vector_weight: float = 0.5,
) -> list[tuple[int, float]]:
    """Weighted sum of clamped cosine and max-normalised BM25.

    ``vector_weight`` is the share that comes from FAISS (1.0 ignores keywords,
    0.0 ignores vectors). A chunk missing from one dict scores 0 on that side.
    Ties break by chunk id so the order is stable.
    """
    if not 0.0 <= vector_weight <= 1.0:
        raise ValueError("vector_weight must be between 0 and 1")
    keyword_norm = _max_normalize(bm25_scores)
    keyword_weight = 1.0 - vector_weight
    fused: list[tuple[int, float]] = []
    for chunk_id in set(vector_scores) | set(keyword_norm):
        cosine = min(1.0, max(0.0, vector_scores.get(chunk_id, 0.0)))
        keyword = keyword_norm.get(chunk_id, 0.0)
        fused.append((chunk_id, vector_weight * cosine + keyword_weight * keyword))
    fused.sort(key=lambda item: (-item[1], item[0]))
    return fused


def _max_normalize(scores: dict[int, float]) -> dict[int, float]:
    """Divide by the best score so values sit in ``[0, 1]``.

    Max-norm, not min-max: a score of 5 next to a 6 stays about 0.83, instead
    of being stretched down to 0. Non-positive scores become 0.
    """
    if not scores:
        return {}
    peak = max(scores.values())
    if peak <= 0.0:
        return dict.fromkeys(scores, 0.0)
    return {chunk_id: (score / peak if score > 0.0 else 0.0) for chunk_id, score in scores.items()}
