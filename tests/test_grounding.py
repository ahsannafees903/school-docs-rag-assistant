from __future__ import annotations

from app.config import Settings
from app.prompts import NOT_FOUND_ANSWER, SYSTEM_PROMPT, build_messages
from app.providers.base import ChatProvider, ContextChunk, Providers
from app.providers.fake import HashingEmbedder
from app.rag import RAGService


class RecordingChat(ChatProvider):
    """Records whether the LLM was called at all."""

    name = "recording"

    def __init__(self, reply: str = "Grounded answer [1]") -> None:
        self.calls: list[tuple[str, list[ContextChunk]]] = []
        self.reply = reply

    def answer(self, question: str, contexts: list[ContextChunk]) -> str:
        self.calls.append((question, contexts))
        return self.reply


def _service(settings: Settings, chat: ChatProvider, min_score: float = 0.15) -> RAGService:
    return RAGService(settings, Providers(HashingEmbedder(), chat, min_score))


def test_answer_cites_sources(loaded_service: RAGService) -> None:
    result = loaded_service.answer("What is the late fee if tuition is paid after the 10th?")
    assert result.grounded is True
    assert "500 PKR" in result.answer
    assert result.sources[0].document_name == "fee_structure_2026-27.pdf"
    assert result.sources[0].page == 2
    assert result.sources[0].snippet


def test_out_of_scope_question_is_refused_without_calling_llm(settings: Settings) -> None:
    chat = RecordingChat()
    service = _service(settings, chat)
    service.ingest("fees.txt", b"The late fee is 500 PKR after the 10th of the month.")
    result = service.answer("Who won the football world cup in 2022?")
    assert result.grounded is False
    assert result.answer == NOT_FOUND_ANSWER
    assert result.sources == []
    assert chat.calls == []


def test_empty_index_is_refused(service: RAGService) -> None:
    result = service.answer("What is the late fee?")
    assert result.grounded is False
    assert result.answer == NOT_FOUND_ANSWER


def test_only_chunks_above_threshold_reach_the_llm(settings: Settings) -> None:
    chat = RecordingChat()
    service = _service(settings, chat, min_score=0.3)
    service.ingest("fees.txt", b"The late fee is 500 PKR after the 10th of the month.")
    service.ingest("sports.txt", b"Football practice is on Thursday afternoons.")
    result = service.answer("What is the late fee after the 10th?")
    assert result.grounded is True
    ((_, contexts),) = chat.calls
    assert [c.document_name for c in contexts] == ["fees.txt"]
    assert [s.document_name for s in result.sources] == ["fees.txt"]


def test_llm_refusal_returns_no_sources(settings: Settings) -> None:
    service = _service(settings, RecordingChat(reply=NOT_FOUND_ANSWER), min_score=0.0)
    service.ingest("fees.txt", b"The late fee is 500 PKR.")
    result = service.answer("late fee")
    assert result.grounded is False
    assert result.sources == []


def test_prompt_forbids_outside_knowledge() -> None:
    assert "ONLY" in SYSTEM_PROMPT
    assert NOT_FOUND_ANSWER in SYSTEM_PROMPT
    messages = build_messages("Q?", [ContextChunk(1, "fees.pdf", 2, "Late fee is 500 PKR.")])
    assert messages[0]["role"] == "system"
    assert "[1] (fees.pdf, page 2)" in messages[1]["content"]
    assert messages[1]["content"].endswith("Question: Q?")
