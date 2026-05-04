"""Structured logging support with privacy-safe JSON and trace-id context."""
from __future__ import annotations

import contextvars
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_TRACE_ID_CTX: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "veritas_trace_id",
    default=None,
)


class VeritasJsonFormatter(logging.Formatter):
    """Privacy-safe structured JSON formatter for operational logs."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": trace_id,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            exc_type = record.exc_info[0]
            payload["exc_type"] = exc_type.__name__ if exc_type is not None else None
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def set_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    """Set the request-local trace id and return reset token."""
    return _TRACE_ID_CTX.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    """Reset the request-local trace id using a token."""
    _TRACE_ID_CTX.reset(token)


def get_trace_id() -> str | None:
    """Get the request-local trace id from context."""
    return _TRACE_ID_CTX.get()


def configure_logging_from_env(force: bool = False) -> None:
    """Configure root logging format based on VERITAS_LOG_FORMAT env.

    Supported values are ``text`` and ``json``. Any other value falls back to
    text and emits a warning via module logger.
    """
    desired = (os.getenv("VERITAS_LOG_FORMAT", "text") or "text").strip().lower()
    if desired not in {"text", "json"}:
        logging.getLogger(__name__).warning(
            "Invalid VERITAS_LOG_FORMAT=%r. Falling back to text.",
            desired,
        )
        desired = "text"

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO)

    if desired == "json":
        formatter = VeritasJsonFormatter()
        for handler in root_logger.handlers:
            if force or not isinstance(handler.formatter, VeritasJsonFormatter):
                handler.setFormatter(formatter)
