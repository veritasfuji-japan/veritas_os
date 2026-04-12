"""Reporting export helpers for compliance artifacts."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from veritas_os.core.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class PipelineTraceSession:
    """OpenTelemetry trace session for one pipeline execution.

    The session creates a root span keyed by ``request_id`` and provides a
    stage-level span context manager so each pipeline phase can be traced
    end-to-end with a consistent request correlation id.
    """

    request_id: str
    user_id: str
    _tracer: Any = None
    _root_span: Any = None
    _stage_durations_ms: Dict[str, int] = field(default_factory=dict)
    _enabled: bool = False

    @classmethod
    def start(cls, *, request_id: str, user_id: str) -> "PipelineTraceSession":
        """Create and start a trace session.

        Tracing is enabled only when ``VERITAS_ENABLE_OTEL_TRACE`` evaluates to
        true and OpenTelemetry dependencies are available.
        """
        trace_enabled = (os.getenv("VERITAS_ENABLE_OTEL_TRACE") or "0").strip().lower()
        if trace_enabled not in {"1", "true", "yes", "on"}:
            return cls(request_id=request_id, user_id=user_id)
        try:
            from opentelemetry import trace
        except Exception as exc:
            logger.warning("OTel trace requested but unavailable: %s", exc)
            return cls(request_id=request_id, user_id=user_id)

        tracer = trace.get_tracer("veritas_os.pipeline")
        root_span = tracer.start_span("pipeline.run_decide")
        root_span.set_attribute("veritas.request_id", request_id)
        root_span.set_attribute("veritas.user_id", user_id)
        root_span.set_attribute("veritas.component", "pipeline")
        return cls(
            request_id=request_id,
            user_id=user_id,
            _tracer=tracer,
            _root_span=root_span,
            _enabled=True,
        )

    @contextmanager
    def stage(self, stage_name: str) -> Iterator[None]:
        """Trace one pipeline stage as a child span."""
        started = time.perf_counter()
        if not self._enabled or self._tracer is None or self._root_span is None:
            try:
                yield
            finally:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                self._stage_durations_ms[stage_name] = max(0, elapsed_ms)
            return

        from opentelemetry import trace

        with trace.use_span(self._root_span, end_on_exit=False):
            with self._tracer.start_as_current_span(
                f"pipeline.stage.{stage_name}",
                context=None,
            ) as span:
                span.set_attribute("veritas.request_id", self.request_id)
                span.set_attribute("veritas.pipeline.stage", stage_name)
                span.set_attribute("veritas.user_id", self.user_id)
                try:
                    yield
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_attribute("veritas.stage.error", type(exc).__name__)
                    raise
                finally:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    self._stage_durations_ms[stage_name] = max(0, elapsed_ms)
                    span.set_attribute(
                        "veritas.stage.duration_ms",
                        self._stage_durations_ms[stage_name],
                    )

    def finalize(
        self,
        *,
        decision_status: str,
        stage_failures: Optional[list[str]] = None,
    ) -> None:
        """Finalize root span and attach execution summary attributes."""
        if not self._enabled or self._root_span is None:
            return
        failures = list(stage_failures or [])
        self._root_span.set_attribute("veritas.decision_status", decision_status)
        self._root_span.set_attribute("veritas.stage.failure_count", len(failures))
        self._root_span.set_attribute(
            "veritas.stage.failures",
            ",".join(failures),
        )
        self._root_span.set_attribute(
            "veritas.pipeline.stage_durations_ms",
            json.dumps(self._stage_durations_ms, sort_keys=True),
        )
        self._root_span.end()


def build_w3c_prov_document(
    *,
    request_id: str,
    decision_status: str,
    risk: float | None,
    timestamp: str,
    actor: str,
    source: str = "veritas_os.pipeline",
) -> Dict[str, Any]:
    """Build a compact W3C PROV JSON document for one decision trace.

    The output follows PROV-JSON style keys so audit systems can ingest the
    decision lineage without binding to internal VERITAS schemas.
    """
    risk_value = 0.0 if risk is None else max(0.0, min(1.0, float(risk)))
    activity_id = f"activity:decision:{request_id}"
    entity_id = f"entity:decision:{request_id}"
    agent_id = f"agent:{actor or 'unknown'}"

    return {
        "prefix": {
            "prov": "http://www.w3.org/ns/prov#",
            "veritas": "https://veritas-os.example/ns#",
        },
        "entity": {
            entity_id: {
                "prov:type": "veritas:Decision",
                "veritas:request_id": request_id,
                "veritas:decision_status": decision_status,
                "veritas:risk": risk_value,
                "prov:generatedAtTime": timestamp,
                "veritas:source": source,
            }
        },
        "activity": {
            activity_id: {
                "prov:type": "veritas:DecisionEvaluation",
                "prov:startedAtTime": timestamp,
                "prov:endedAtTime": timestamp,
            }
        },
        "agent": {
            agent_id: {
                "prov:type": "prov:SoftwareAgent",
                "prov:label": actor,
            }
        },
        "wasGeneratedBy": {
            f"wgb:{request_id}": {
                "prov:entity": entity_id,
                "prov:activity": activity_id,
            }
        },
        "wasAssociatedWith": {
            f"waw:{request_id}": {
                "prov:activity": activity_id,
                "prov:agent": agent_id,
            }
        },
    }


def _escape_pdf_text(value: str) -> str:
    """Escape PDF text operators for literal text rendering."""
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_pdf_bytes(report: Dict[str, Any]) -> bytes:
    """Build a compact audit PDF from report content.

    This exporter intentionally emits a simple single-page PDF for portability
    in restricted runtime environments where external PDF engines may be
    unavailable.
    """
    lines = [
        "VERITAS OS Compliance Report",
        f"Report Type: {report.get('report_type', 'unknown')}",
        f"Generated At: {report.get('generated_at', 'unknown')}",
        "---",
    ]
    summary = json.dumps(report.get("summary", {}), ensure_ascii=True, sort_keys=True)
    lines.extend([summary[i:i + 100] for i in range(0, len(summary), 100)])

    text_ops = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    for index, line in enumerate(lines):
        escaped = _escape_pdf_text(line)
        if index == 0:
            text_ops.append(f"({escaped}) Tj")
        else:
            text_ops.append(f"T* ({escaped}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("utf-8")

    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n",
        b"4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        f"5 0 obj<< /Length {len(stream)} >>stream\n".encode("utf-8")
        + stream
        + b"\nendstream\nendobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("utf-8"))

    pdf.extend(
        (
            f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(pdf)


def persist_report_json(path: Path, payload: Dict[str, Any]) -> None:
    """Persist report JSON with atomic write guarantees."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload, indent=2)


def persist_report_pdf(path: Path, payload: Dict[str, Any]) -> None:
    """Persist report PDF bytes to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_pdf_bytes(payload))
