"""The JSON response envelope used by every endpoint. See docs/API_STANDARDS.md."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError

logger = logging.getLogger(__name__)

HTTP_CODE_NAMES: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_FILE_TYPE",
    422: "VALIDATION_ERROR",
}


def success(data: Any, status_code: int = 200) -> JSONResponse:
    body = {"status": "success", "data": jsonable_encoder(data), "error": None}
    return JSONResponse(status_code=status_code, content=body)


def error(code: str, message: str, status_code: int) -> JSONResponse:
    body = {"status": "error", "data": None, "error": {"code": code, "message": message}}
    return JSONResponse(status_code=status_code, content=body)


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or "Invalid request"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error("VALIDATION_ERROR", _validation_message(exc), 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
        return error(code, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        return error("INTERNAL_ERROR", "An unexpected error occurred.", 500)
