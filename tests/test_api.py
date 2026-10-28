from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response
from simple_pdf import build_pdf

from app.config import Settings
from app.prompts import NOT_FOUND_ANSWER


def assert_success(body: dict) -> object:
    assert set(body) == {"status", "data", "error"}
    assert body["status"] == "success"
    assert body["error"] is None
    return body["data"]


def assert_error(body: dict, code: str) -> None:
    assert set(body) == {"status", "data", "error"}
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == code
    assert body["error"]["message"]


def upload(client: TestClient, name: str, content: bytes, mime: str = "text/plain") -> Response:
    return client.post("/documents", files={"file": (name, content, mime)})


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = assert_success(res.json())
    assert data["provider"] == "fake"


def test_upload_list_delete_flow(client: TestClient) -> None:
    pdf = build_pdf([["Tuition is due by the 10th."], ["A late fee of 500 PKR applies."]])
    res = upload(client, "fees.pdf", pdf, "application/pdf")
    assert res.status_code == 201
    doc = assert_success(res.json())
    assert doc["filename"] == "fees.pdf"
    assert doc["pages"] == 2

    listed = assert_success(client.get("/documents").json())
    assert [d["id"] for d in listed] == [doc["id"]]

    res = client.delete(f"/documents/{doc['id']}")
    assert res.status_code == 200
    assert assert_success(res.json()) == {"id": doc["id"], "deleted": True}
    assert assert_success(client.get("/documents").json()) == []


def test_chat_returns_answer_and_sources(client: TestClient) -> None:
    upload(client, "exam_rules.md", b"Mobile phones are strictly not allowed in the exam hall.")
    res = client.post("/chat", json={"question": "Are mobile phones allowed in the exam hall?"})
    assert res.status_code == 200
    data = assert_success(res.json())
    assert data["grounded"] is True
    assert "Mobile phones" in data["answer"]
    source = data["sources"][0]
    assert set(source) == {"document_id", "document_name", "page", "snippet", "score"}
    assert source["document_name"] == "exam_rules.md"
    assert source["page"] is None


def test_chat_refusal_is_still_success_envelope(client: TestClient) -> None:
    upload(client, "fees.txt", b"The late fee is 500 PKR.")
    data = assert_success(client.post("/chat", json={"question": "Capital of Australia?"}).json())
    assert data == {"answer": NOT_FOUND_ANSWER, "grounded": False, "sources": []}


def test_unsupported_file_type(client: TestClient) -> None:
    res = upload(client, "photo.png", b"\x89PNG", "image/png")
    assert res.status_code == 415
    assert_error(res.json(), "UNSUPPORTED_FILE_TYPE")


def test_empty_file(client: TestClient) -> None:
    res = upload(client, "empty.txt", b"")
    assert res.status_code == 422
    assert_error(res.json(), "EMPTY_DOCUMENT")


def test_missing_file_field(client: TestClient) -> None:
    res = client.post("/documents")
    assert res.status_code == 422
    assert_error(res.json(), "VALIDATION_ERROR")


def test_blank_question(client: TestClient) -> None:
    res = client.post("/chat", json={"question": "   "})
    assert res.status_code == 422
    assert_error(res.json(), "VALIDATION_ERROR")


def test_invalid_json_body(client: TestClient) -> None:
    res = client.post("/chat", content=b"not json", headers={"content-type": "application/json"})
    assert res.status_code == 422
    assert_error(res.json(), "VALIDATION_ERROR")


def test_delete_unknown_document(client: TestClient) -> None:
    res = client.delete("/documents/doesnotexist")
    assert res.status_code == 404
    assert_error(res.json(), "NOT_FOUND")


def test_unknown_route_and_method(client: TestClient) -> None:
    res = client.get("/nope")
    assert res.status_code == 404
    assert_error(res.json(), "NOT_FOUND")
    res = client.put("/health")
    assert res.status_code == 405
    assert_error(res.json(), "METHOD_NOT_ALLOWED")


def test_provider_error_uses_envelope(client: TestClient) -> None:
    from app.errors import ProviderError

    def boom(_: list[str]) -> list[list[float]]:
        raise ProviderError("Could not reach Ollama")

    client.app.state.rag.providers.embedder.embed = boom  # type: ignore[attr-defined]
    res = client.post("/chat", json={"question": "late fee?"})
    assert res.status_code == 502
    assert_error(res.json(), "PROVIDER_ERROR")


def test_unexpected_error_is_wrapped(settings: Settings) -> None:
    from app.main import create_app
    from app.rag import RAGService

    class Broken(RAGService):
        def list_documents(self) -> list:
            raise RuntimeError("disk on fire")

    client = TestClient(create_app(settings, Broken(settings)), raise_server_exceptions=False)
    res = client.get("/documents")
    assert res.status_code == 500
    assert_error(res.json(), "INTERNAL_ERROR")
    assert "disk on fire" not in res.text


def test_ui_is_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "School Docs Assistant" in res.text
    assert client.get("/static/app.js").status_code == 200


def test_request_id_header(client: TestClient) -> None:
    res = client.get("/health", headers={"x-request-id": "abc123"})
    assert res.headers["x-request-id"] == "abc123"
