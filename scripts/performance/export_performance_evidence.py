"""Exporter for reviewer-facing performance evidence payloads.

This module is intentionally CI-safe and avoids external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
import math
from statistics import mean
from time import perf_counter
from typing import Any, Callable


FIXED_GENERATED_AT = "1970-01-01T00:00:00+00:00"

OUTPUT_JSON = Path("docs/en/validation/performance-evidence.latest.json")
OUTPUT_MD = Path("docs/en/validation/performance-evidence.latest.md")


@dataclass(frozen=True)
class _HttpResult:
    status_code: int
    body: str = ""


def _parse_generated_at(generated_at: str | None) -> str:
    if generated_at is None:
        return datetime.now(timezone.utc).isoformat()
    value = str(generated_at).strip()
    if value == "":
        raise ValueError("generated_at must be a non-empty ISO-8601 string")
    candidate = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("generated_at must be a valid ISO-8601 datetime") from exc
    return value


def percentile(values: list[float], pct: float) -> float:
    """Return nearest-rank percentile for inclusive pct range [0.0, 1.0]."""
    if not values:
        raise ValueError("values must not be empty")
    if pct < 0.0 or pct > 1.0:
        raise ValueError("pct must be between 0.0 and 1.0")
    ordered = sorted(values)
    rank = math.ceil(pct * len(ordered))
    index = max(0, rank - 1)
    return ordered[index]


def _assert_http_status(result: _HttpResult) -> None:
    if result.status_code != 200:
        raise RuntimeError(f"unexpected status code: {result.status_code}")


def measure_latency(name: str, fn: Callable[[], Any], sample_count: int) -> dict[str, Any]:
    """Measure latency and convert exceptions into failed metric records."""
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")

    samples: list[float] = []
    try:
        for _ in range(sample_count):
            started = perf_counter()
            fn()
            duration_ms = (perf_counter() - started) * 1000
            samples.append(round(duration_ms, 6))
    except Exception as exc:  # noqa: BLE001 - exported as structured failure
        return {
            "name": name,
            "status": "failed",
            "samples": samples,
            "summary": None,
            "notes": f"error_type={exc.__class__.__name__}",
        }

    return {
        "name": name,
        "status": "ok",
        "samples": samples,
        "summary": {
            "avg_ms": round(mean(samples), 6),
            "p50_ms": round(percentile(samples, 0.50), 6),
            "p95_ms": round(percentile(samples, 0.95), 6),
            "p99_ms": round(percentile(samples, 0.99), 6),
        },
        "notes": "",
    }


def export_performance_evidence(
    *,
    deterministic_fixture: bool,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build performance evidence artifact payload for reviewers.

    With deterministic_fixture enabled, no external service is called.
    """
    effective_generated_at = (
        FIXED_GENERATED_AT
        if deterministic_fixture and generated_at is None
        else generated_at
    )
    timestamp = _parse_generated_at(effective_generated_at)

    if deterministic_fixture:
        measurement_mode = "deterministic_fixture"
        sample_count = 3
        warmup_count = 0

        fixtures = {
            "api_health_route": [8.1, 8.3, 8.2],
            "trustlog_append_local": [3.1, 3.3, 3.2],
            "bind_eval_local": [4.2, 4.1, 4.3],
        }
        metrics = [
            {
                "name": key,
                "status": "ok",
                "samples": vals,
                "summary": {
                    "avg_ms": round(mean(vals), 6),
                    "p50_ms": round(percentile(vals, 0.50), 6),
                    "p95_ms": round(percentile(vals, 0.95), 6),
                    "p99_ms": round(percentile(vals, 0.99), 6),
                },
                "notes": "deterministic fixture; not production SLA",
            }
            for key, vals in fixtures.items()
        ]
    else:
        measurement_mode = "not_measured"
        sample_count = 0
        warmup_count = 0
        metrics = []

    return {
        "schema_version": "performance_evidence.v1",
        "generated_at": timestamp,
        "measurement_mode": measurement_mode,
        "sample_count": sample_count,
        "warmup_count": warmup_count,
        "metrics": metrics,
        "notes": [
            "Reviewer-facing operational evidence only.",
            "Not a production SLA statement.",
        ],
    }


def _markdown_table_cell(value: Any) -> str:
    """Escape markdown table cell separators and newlines."""
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def render_performance_markdown(payload: dict[str, Any]) -> str:
    """Render markdown report for reviewers from payload."""
    lines = [
        "# Performance Evidence",
        "",
        "## Summary table",
        "| Key | Value |",
        "| --- | --- |",
    ]
    summary_rows = [
        ("schema_version", payload["schema_version"]),
        ("generated_at", payload["generated_at"]),
        ("measurement_mode", payload["measurement_mode"]),
        ("sample_count", payload["sample_count"]),
        ("warmup_count", payload["warmup_count"]),
    ]
    for key, value in summary_rows:
        lines.append(
            f"| {_markdown_table_cell(key)} | {_markdown_table_cell(value)} |"
        )

    lines.extend([
        "",
        "## Metrics table",
        "| Metric | Status | Samples | p95_ms | Notes |",
        "| --- | --- | --- | --- | --- |",
    ])
    for metric in payload["metrics"]:
        p95 = ""
        if metric["summary"] is not None:
            p95 = str(metric["summary"]["p95_ms"])
        name = _markdown_table_cell(metric["name"])
        status = _markdown_table_cell(metric["status"])
        p95_cell = _markdown_table_cell(p95)
        notes = _markdown_table_cell(metric["notes"])
        lines.append(
            f"| {name} | {status} | {len(metric['samples'])} | {p95_cell} | {notes} |"
        )
    measurement_mode = payload.get("measurement_mode")
    if measurement_mode == "deterministic_fixture":
        boundary_lines = [
            "- This artifact is reviewer-facing deterministic fixture evidence.",
            "- This artifact is not a production SLA.",
            "- This artifact does not include external LLM provider latency.",
            "- This artifact does not include customer infrastructure latency.",
            "- Results should be re-measured in customer PoC environments.",
            "- This artifact is intended to validate exporter structure, reporting format, and deterministic evidence plumbing.",
        ]
    else:
        boundary_lines = [
            "- This artifact is reviewer-facing operational evidence.",
            "- This artifact is not a production SLA.",
            "- This artifact does not include external LLM provider latency unless explicitly measured.",
            "- This artifact does not include customer infrastructure latency.",
            "- Results should be re-measured in customer PoC environments.",
        ]

    lines.extend(["", "## Interpretation boundaries", *boundary_lines])
    return "\n".join(lines) + "\n"


def write_performance_evidence(
    json_path: Path = OUTPUT_JSON,
    markdown_path: Path = OUTPUT_MD,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write deterministic reviewer-facing fixture artifacts to JSON and Markdown files."""
    payload = export_performance_evidence(
        deterministic_fixture=True,
        generated_at=generated_at,
    )
    markdown = render_performance_markdown(payload)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(markdown.rstrip("\n") + "\n", encoding="utf-8")
    return payload


def main() -> int:
    """Generate committed reviewer-facing performance evidence artifacts."""
    write_performance_evidence()
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "export_performance_evidence",
    "measure_latency",
    "percentile",
    "render_performance_markdown",
    "write_performance_evidence",
    "main",
]
