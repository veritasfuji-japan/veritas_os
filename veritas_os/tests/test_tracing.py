"""Tests for veritas_os.observability.tracing — distributed tracing helpers."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestTracingConfiguration:
    """Test trace exporter configuration."""

    def test_trace_exporter_mode_default(self):
        from veritas_os.observability.tracing import _trace_exporter_mode

        with patch.dict(os.environ, {}, clear=True):
            assert _trace_exporter_mode() == "none"

    def test_trace_exporter_mode_from_env(self):
        from veritas_os.observability.tracing import _trace_exporter_mode

        with patch.dict(os.environ, {"VERITAS_TRACE_EXPORTER": "otlp"}):
            assert _trace_exporter_mode() == "otlp"

    def test_trace_exporter_mode_stripped(self):
        from veritas_os.observability.tracing import _trace_exporter_mode

        with patch.dict(os.environ, {"VERITAS_TRACE_EXPORTER": "  Console  "}):
            assert _trace_exporter_mode() == "console"

    def test_service_name_default(self):
        from veritas_os.observability.tracing import _service_name

        with patch.dict(os.environ, {}, clear=True):
            assert _service_name() == "veritas-os"

    def test_service_name_custom(self):
        from veritas_os.observability.tracing import _service_name

        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "my-service"}):
            assert _service_name() == "my-service"

    def test_configure_trace_exporter_none(self):
        from veritas_os.observability.tracing import configure_trace_exporter

        with patch.dict(os.environ, {"VERITAS_TRACE_EXPORTER": "none"}):
            result = configure_trace_exporter()
            assert result == "none"


class TestSpanHelpers:
    """Test span context managers and helper functions."""

    def test_pipeline_root_span_noop_when_disabled(self):
        """Root span should yield None when tracing is disabled."""
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        try:
            tracing._tracer = None
            with tracing.pipeline_root_span("req-123") as span:
                assert span is None
        finally:
            tracing._tracer = original_tracer

    def test_pipeline_stage_span_noop_when_disabled(self):
        """Stage span should yield None when tracing is disabled."""
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        try:
            tracing._tracer = None
            with tracing.pipeline_stage_span("input_norm") as span:
                assert span is None
        finally:
            tracing._tracer = original_tracer

    def test_record_span_event_noop_when_span_is_none(self):
        """record_span_event should be a no-op when span is None."""
        from veritas_os.observability.tracing import record_span_event

        # Should not raise
        record_span_event(None, "test_event", {"key": "value"})

    def test_record_span_event_calls_add_event(self):
        """record_span_event should call add_event on a real span."""
        from veritas_os.observability.tracing import record_span_event

        mock_span = MagicMock()
        record_span_event(mock_span, "test_event", {"key": "value"})
        mock_span.add_event.assert_called_once_with("test_event", attributes={"key": "value"})

    def test_set_span_attribute_noop_when_span_is_none(self):
        """set_span_attribute should be a no-op when span is None."""
        from veritas_os.observability.tracing import set_span_attribute

        # Should not raise
        set_span_attribute(None, "key", "value")

    def test_set_span_attribute_calls_set_attribute(self):
        """set_span_attribute should call set_attribute on a real span."""
        from veritas_os.observability.tracing import set_span_attribute

        mock_span = MagicMock()
        set_span_attribute(mock_span, "key", "value")
        mock_span.set_attribute.assert_called_once_with("key", "value")

    def test_pipeline_root_span_with_mock_tracer(self):
        """Root span should create a span when tracer is available."""
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        try:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            tracing._tracer = mock_tracer

            with tracing.pipeline_root_span(
                "req-456",
                query="test query",
                user_id="user-1",
                fast_mode=True,
            ) as span:
                assert span is mock_span

            mock_tracer.start_as_current_span.assert_called_once()
            call_kwargs = mock_tracer.start_as_current_span.call_args
            assert call_kwargs[0][0] == "decide_pipeline"
            attrs = call_kwargs[1]["attributes"]
            assert attrs["veritas.request_id"] == "req-456"
            assert attrs["veritas.query"] == "test query"
            assert attrs["veritas.user_id"] == "user-1"
            assert attrs["veritas.fast_mode"] is True
        finally:
            tracing._tracer = original_tracer

    def test_pipeline_root_span_truncates_long_query(self):
        """Root span should truncate queries longer than 256 characters."""
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        try:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            tracing._tracer = mock_tracer

            long_query = "a" * 500
            with tracing.pipeline_root_span("req-789", query=long_query):
                pass

            attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]
            assert len(attrs["veritas.query"]) == 256
        finally:
            tracing._tracer = original_tracer

    def test_pipeline_stage_span_with_mock_tracer(self):
        """Stage span should create a child span when tracer is available."""
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        try:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
            mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
            tracing._tracer = mock_tracer

            with tracing.pipeline_stage_span("input_norm", attributes={"custom": "attr"}) as span:
                assert span is mock_span

            mock_tracer.start_as_current_span.assert_called_once_with(
                "pipeline.input_norm",
                attributes={"custom": "attr"},
            )
        finally:
            tracing._tracer = original_tracer


class TestShutdown:
    """Test tracing shutdown."""

    def test_shutdown_tracing_clears_state(self):
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        original_provider = tracing._provider
        try:
            tracing._tracer = MagicMock()
            tracing._provider = MagicMock()
            tracing.shutdown_tracing()
            assert tracing._tracer is None
            assert tracing._provider is None
        finally:
            tracing._tracer = original_tracer
            tracing._provider = original_provider

    def test_shutdown_tracing_noop_when_not_configured(self):
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        original_provider = tracing._provider
        try:
            tracing._tracer = None
            tracing._provider = None
            # Should not raise
            tracing.shutdown_tracing()
        finally:
            tracing._tracer = original_tracer
            tracing._provider = original_provider

    def test_shutdown_tracing_handles_provider_error(self):
        from veritas_os.observability import tracing

        original_tracer = tracing._tracer
        original_provider = tracing._provider
        try:
            mock_provider = MagicMock()
            mock_provider.shutdown.side_effect = RuntimeError("shutdown failed")
            tracing._tracer = MagicMock()
            tracing._provider = mock_provider
            # Should not raise
            tracing.shutdown_tracing()
            assert tracing._tracer is None
            assert tracing._provider is None
        finally:
            tracing._tracer = original_tracer
            tracing._provider = original_provider


class TestPipelineFallbackSpans:
    """Test the no-op fallback spans used in pipeline when tracing is unavailable."""

    def test_fallback_pipeline_root_span(self):
        """Pipeline fallback root span should yield None."""
        from veritas_os.core.pipeline import (
            _pipeline_root_span,
        )

        with _pipeline_root_span("test-req") as span:
            # Span may be None (fallback) or a real span object depending
            # on whether OpenTelemetry is installed. Either way it should
            # not raise.
            pass

    def test_fallback_pipeline_stage_span(self):
        """Pipeline fallback stage span should yield None."""
        from veritas_os.core.pipeline import (
            _pipeline_stage_span,
        )

        with _pipeline_stage_span("test_stage") as span:
            pass

    def test_fallback_record_span_event(self):
        """Pipeline fallback record_span_event should be a no-op."""
        from veritas_os.core.pipeline import _record_span_event

        _record_span_event(None, "test")

    def test_fallback_set_span_attribute(self):
        """Pipeline fallback set_span_attribute should be a no-op."""
        from veritas_os.core.pipeline import _set_span_attribute

        _set_span_attribute(None, "key", "value")
