"""VERITAS OS observability integration package."""

from veritas_os.observability.exporters import configure_metrics_exporter
from veritas_os.observability.pg_collector import collect_all_pg_metrics
from veritas_os.observability.tracing import (
    configure_trace_exporter,
    get_tracer,
    pipeline_root_span,
    pipeline_stage_span,
    record_span_event,
    set_span_attribute,
    shutdown_tracing,
)

__all__ = [
    "configure_metrics_exporter",
    "collect_all_pg_metrics",
    "configure_trace_exporter",
    "get_tracer",
    "pipeline_root_span",
    "pipeline_stage_span",
    "record_span_event",
    "set_span_attribute",
    "shutdown_tracing",
]
