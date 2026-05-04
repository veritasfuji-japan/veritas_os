"""Unit tests for privacy-safe structured logging and trace propagation."""
from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import Response

from veritas_os.api.middleware import TRACE_ID_HEADER_NAME, attach_trace_id
from veritas_os.logging.structured import (
    VeritasJsonFormatter,
    configure_logging_from_env,
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)


def _build_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_json_formatter_emits_valid_json() -> None:
    formatter = VeritasJsonFormatter()
    record = logging.LogRecord(
        name="veritas.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello %s",
        args=("world",),
        exc_info=None,
        func="test_func",
    )

    payload = json.loads(formatter.format(record))

    assert payload["ts"].endswith("Z")
    assert payload["level"] == "INFO"
    assert payload["logger"] == "veritas.test"
    assert payload["msg"] == "hello world"
    assert payload["trace_id"] is None
    assert payload["module"]
    assert payload["function"] == "test_func"
    assert payload["line"] == 12


def test_json_formatter_does_not_dump_unsafe_extras() -> None:
    formatter = VeritasJsonFormatter()
    record = logging.LogRecord(
        name="veritas.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=22,
        msg="event",
        args=(),
        exc_info=None,
        func="test_func",
    )
    record.Authorization = "Bearer secret"
    record.token = "tok"
    record.query_string = "x=1"
    record.Cookie = "cookie"

    rendered = formatter.format(record)
    payload = json.loads(rendered)

    assert "Authorization" not in payload
    assert "token" not in payload
    assert "query_string" not in payload
    assert "Cookie" not in payload
    assert "secret" not in rendered


def test_context_trace_id_is_included_and_reset() -> None:
    formatter = VeritasJsonFormatter()
    token = set_trace_id("trace-test")
    try:
        record = logging.LogRecord(
            name="veritas.test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=31,
            msg="warn",
            args=(),
            exc_info=None,
            func="test_func",
        )
        payload = json.loads(formatter.format(record))
        assert payload["trace_id"] == "trace-test"
    finally:
        reset_trace_id(token)

    record = logging.LogRecord(
        name="veritas.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=33,
        msg="plain",
        args=(),
        exc_info=None,
        func="test_func",
    )
    payload = json.loads(formatter.format(record))
    assert payload["trace_id"] is None


async def test_attach_trace_id_sets_and_resets_contextvar() -> None:
    request = _build_request(headers=[(b"x-trace-id", b"traceabc1")])

    async def call_next(_: Request) -> Response:
        assert get_trace_id() == "traceabc1"
        return Response(content="ok")

    response = await attach_trace_id(request, call_next)

    assert response.headers[TRACE_ID_HEADER_NAME] == "traceabc1"
    assert response.headers["X-Request-Id"] == "traceabc1"
    assert get_trace_id() is None


def test_configure_logging_json(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "json")
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    handler = logging.StreamHandler()
    root.handlers = [handler]
    try:
        configure_logging_from_env(force=True)
        assert isinstance(root.handlers[0].formatter, VeritasJsonFormatter)
    finally:
        root.handlers = old_handlers


def test_configure_logging_invalid_value_falls_back_to_text(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_LOG_FORMAT", "bad")
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    handler = logging.StreamHandler()
    root.handlers = [handler]
    configure_logging_from_env(force=True)
    try:
        assert not isinstance(root.handlers[0].formatter, VeritasJsonFormatter)
    finally:
        root.handlers = old_handlers


def test_configure_logging_default_text(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_LOG_FORMAT", raising=False)
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    handler = logging.StreamHandler()
    root.handlers = [handler]
    try:
        configure_logging_from_env(force=True)
        assert not isinstance(root.handlers[0].formatter, VeritasJsonFormatter)
    finally:
        root.handlers = old_handlers
