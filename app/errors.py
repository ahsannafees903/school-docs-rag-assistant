"""Application error type with a stable, machine-readable error code."""

from __future__ import annotations


class AppError(Exception):
    """An expected error that maps to a JSON error envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProviderError(AppError):
    """Raised when an embedding or chat provider fails (network, auth, bad response)."""

    def __init__(self, message: str) -> None:
        super().__init__("PROVIDER_ERROR", message, status_code=502)
