"""Reporting export helpers for compliance artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from veritas_os.core.atomic_io import atomic_write_json


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
