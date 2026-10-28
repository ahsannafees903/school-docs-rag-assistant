"""Prompt used by the real LLM providers. The rules keep answers grounded."""

from __future__ import annotations

from app.providers.base import ContextChunk

NOT_FOUND_ANSWER = (
    "I couldn't find the answer to that in the uploaded documents. "
    "Try rephrasing, or upload the document that covers it."
)

SYSTEM_PROMPT = f"""You are School Docs Assistant. You answer questions about a school's \
documents for parents, students and staff.

Rules:
1. Use ONLY the numbered context passages below. Do not use outside knowledge.
2. If the context does not contain the answer, reply exactly: "{NOT_FOUND_ANSWER}"
3. Cite the passages you used with their numbers in square brackets, e.g. [1] or [2][3].
4. Be concise: 1-4 sentences, or a short list for multi-part answers.
5. Never invent fees, dates, names or rules that are not written in the context."""


def format_context(contexts: list[ContextChunk]) -> str:
    blocks = []
    for c in contexts:
        where = f"{c.document_name}, page {c.page}" if c.page else c.document_name
        blocks.append(f"[{c.number}] ({where})\n{c.text}")
    return "\n\n".join(blocks)


def build_messages(question: str, contexts: list[ContextChunk]) -> list[dict[str, str]]:
    user = f"Context passages:\n\n{format_context(contexts)}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
