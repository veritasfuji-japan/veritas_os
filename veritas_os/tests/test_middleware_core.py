# tests for veritas_os/api/middleware.py — pure functions
"""Tests for middleware utility functions."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from veritas_os.api.middleware import (
    _resolve_max_request_body_size,
    _resolve_trace_id_from_request,
    _inflight_snapshot,
    TRACE_ID_HEADER_NAME,
    MAX_REQUEST_BODY_SIZE,
)


class TestResolveMaxRequestBodySize:
    def test_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_ENV", None)
            os.environ.pop("VERITAS_MAX_REQUEST_BODY_SIZE", None)
            size = _resolve_max_request_body_size()
        assert size == 10 * 1024 * 1024

    def test_production_profile(self):
        with mock.patch.dict(os.environ, {"VERITAS_ENV": "production"}):
            os.environ.pop("VERITAS_MAX_REQUEST_BODY_SIZE", None)
            size = _resolve_max_request_body_size()
        assert size == 5 * 1024 * 1024

    def test_explicit_override(self):
        with mock.patch.dict(os.environ, {"VERITAS_MAX_REQUEST_BODY_SIZE": "1000"}):
            size = _resolve_max_request_body_size()
        assert size == 1000

    def test_invalid_override(self):
        with mock.patch.dict(os.environ, {"VERITAS_MAX_REQUEST_BODY_SIZE": "bad"}):
            size = _resolve_max_request_body_size()
        assert size > 0

    def test_negative_override(self):
        with mock.patch.dict(os.environ, {"VERITAS_MAX_REQUEST_BODY_SIZE": "-1"}):
            size = _resolve_max_request_body_size()
        assert size > 0


class TestResolveTraceId:
    def test_from_header(self):
        req = mock.MagicMock()
        req.headers.get.side_effect = lambda name: "abc12345-trace-id" if name == TRACE_ID_HEADER_NAME else None
        trace_id = _resolve_trace_id_from_request(req)
        assert trace_id == "abc12345-trace-id"

    def test_generates_when_missing(self):
        req = mock.MagicMock()
        req.headers.get.return_value = None
        trace_id = _resolve_trace_id_from_request(req)
        assert len(trace_id) == 32  # hex(16 bytes)

    def test_rejects_invalid_trace_id(self):
        req = mock.MagicMock()
        req.headers.get.side_effect = lambda name: "bad!" if name == TRACE_ID_HEADER_NAME else None
        trace_id = _resolve_trace_id_from_request(req)
        assert len(trace_id) == 32  # Generated a new one


class TestInflightSnapshot:
    def test_returns_dict(self):
        snap = _inflight_snapshot()
        assert "inflight" in snap
        assert "shutting_down" in snap
