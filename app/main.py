"""FastAPI application: routes, middleware and static chat UI.

Run with: ``uvicorn app.main:create_app --factory``
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import Settings, get_settings
from app.envelope import register_exception_handlers, success
from app.logging_config import configure_logging
from app.models import ChatRequest
from app.rag import RAGService

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger("app.request")


def create_app(settings: Settings | None = None, service: RAGService | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    rag = service or RAGService(settings)

    app = FastAPI(
        title="School Docs Assistant",
        version=__version__,
        description="Ask questions about school documents and get answers with citations.",
    )
    app.state.rag = rag
    register_exception_handlers(app)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        if not request.url.path.startswith("/static"):
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        return success(
            {
                "service": "school-docs-assistant",
                "version": __version__,
                "provider": settings.provider,
                "min_score": rag.min_score,
            }
        )

    @app.post("/documents", status_code=201)
    async def upload_document(file: UploadFile = File(...)) -> JSONResponse:  # noqa: B008
        content = await file.read(settings.max_upload_bytes + 1)
        document = rag.ingest(file.filename or "document", content)
        return success(document, status_code=201)

    @app.get("/documents")
    def list_documents() -> JSONResponse:
        return success(rag.list_documents())

    @app.delete("/documents/{document_id}")
    def delete_document(document_id: str) -> JSONResponse:
        rag.delete_document(document_id)
        return success({"id": document_id, "deleted": True})

    @app.post("/chat")
    def chat(body: ChatRequest) -> JSONResponse:
        return success(rag.answer(body.question, body.top_k))

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
