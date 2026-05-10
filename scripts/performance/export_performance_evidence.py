"""Generate reviewer-facing performance evidence artifacts.

This script provides CI-safe local latency evidence for representative API routes,
Bind boundary checks, and TrustLog append behavior using local/test backends only.
It intentionally does not claim production SLA and does not include external LLM
provider latency or customer infrastructure latency unless explicitly measured.
Deterministic fixture mode exists for freshness/testing stability, not real timing.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_JSON = REPO_ROOT / "docs/en/validation/performance-evidence.latest.json"
OUTPUT_MD = REPO_ROOT / "docs/en/validation/performance-evidence.latest.md"
GENERATED_AT_ERROR_MESSAGE = (
    "generated_at must be a non-empty ISO-8601 timestamp when provided"
)


def _resolve_generated_at(generated_at: str | None) -> str:
    """Resolve artifact timestamp with ISO-8601 validation.

    This validates metadata freshness only and does not change measurement behavior.
    """

    if generated_at is None:
        return datetime.now(timezone.utc).isoformat()
    value = str(generated_at).strip()
    if not value:
        raise ValueError(GENERATED_AT_ERROR_MESSAGE)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(GENERATED_AT_ERROR_MESSAGE) from exc
    return value


def percentile(values: list[float], pct: float) -> float:
    """Return linear-interpolated percentile for ``values``.

    ``pct`` must be in [0.0, 1.0]. Empty input is invalid.
    """

    if not 0.0 <= pct <= 1.0:
        raise ValueError("pct must be within [0.0, 1.0]")
    if not values:
        raise ValueError("values must be non-empty")
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def _assert_status_ok(response: Any, expected_status: int = 200) -> None:
    """Fail route measurement when unexpected HTTP status is returned."""

    if int(getattr(response, "status_code", -1)) != expected_status:
        raise RuntimeError(f"unexpected HTTP status: {getattr(response, 'status_code', -1)}")


def measure_latency(
    name: str,
    category: str,
    fn: Callable[[], Any],
    sample_count: int,
    warmup_count: int,
    notes: str = "",
) -> dict[str, Any]:
    """Measure latency in milliseconds with warmup and safe failure capture.

    Exceptions are converted to ``status=failed`` and expose only error class names.
    """

    try:
        for _ in range(max(0, warmup_count)):
            fn()
        samples: list[float] = []
        for _ in range(max(0, sample_count)):
            start = time.perf_counter_ns()
            fn()
            elapsed = (time.perf_counter_ns() - start) / 1_000_000.0
            samples.append(elapsed)
        return {
            "name": name,
            "category": category,
            "unit": "ms",
            "samples": samples,
            "p50_ms": percentile(samples, 0.50),
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "mean_ms": statistics.fmean(samples),
            "min_ms": min(samples),
            "max_ms": max(samples),
            "status": "ok",
            "notes": notes,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "category": category,
            "unit": "ms",
            "samples": [],
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "status": "failed",
            "notes": f"error_type={exc.__class__.__name__}",
        }


def _fixture_metric(name: str, category: str, samples: list[float], notes: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "unit": "ms",
        "samples": samples,
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "mean_ms": statistics.fmean(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "status": "ok",
        "notes": notes,
    }


def _measure_trustlog_append_fixed_state(sample_count: int, warmup_count: int) -> dict[str, Any]:
    """Measure local TrustLog append latency with per-sample reset fixed-state setup."""

    from veritas_os.api.trust_log_io import append_trust_log_entry, load_logs_json_result, save_json

    logger_obj = type("L", (), {"warning": lambda *a, **k: None, "debug": lambda *a, **k: None})()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        def effective_log_paths() -> tuple[Path, Path, Path]:
            return root, root / "trust_log.json", root / "trust_log.jsonl"

        def _reset_log_state() -> None:
            for path in (root / "trust_log.json", root / "trust_log.jsonl"):
                if path.exists():
                    path.unlink()

        def _append_once() -> None:
            _reset_log_state()

            def _load(path: Path | None):
                return load_logs_json_result(
                    path,
                    max_log_file_size=1024 * 1024,
                    effective_log_paths=effective_log_paths,
                    logger=logger_obj,
                )

            append_trust_log_entry(
                {"kind": "perf", "request_id": "perf-check"},
                effective_log_paths=effective_log_paths,
                has_atomic_io=False,
                atomic_append_line=None,
                load_logs_json_result_fn=_load,
                load_logs_json_fn=lambda _p: [],
                save_json_fn=lambda p, items: save_json(
                    p,
                    items,
                    has_atomic_io=False,
                    atomic_write_json=None,
                    secure_chmod_fn=lambda _x: None,
                ),
                secure_chmod_fn=lambda _x: None,
                publish_event=lambda *_a, **_k: None,
                logger=logger_obj,
                errstr=lambda _e: "error",
            )

        return measure_latency(
            "trustlog.append.local",
            "trustlog_append",
            _append_once,
            sample_count,
            warmup_count,
            notes=(
                "Measured with fixed-state local/test backend; per-sample log reset before append."
            ),
        )


def generate_performance_evidence(
    generated_at: str | None = None,
    sample_count: int = 30,
    warmup_count: int = 3,
    deterministic_fixture: bool = False,
) -> dict[str, Any]:
    """Build performance evidence for reviewer-facing CI-safe/local validation.

    Normal mode measures local API/Bind/TrustLog paths without external providers.
    Deterministic mode returns fixed fixture samples for freshness/testing only.
    """

    env = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
        "ci_detected": bool(
            any(key in os.environ for key in ("CI", "GITHUB_ACTIONS", "BUILD_BUILDID"))
        ),
    }
    failures: list[dict[str, str]] = []

    if deterministic_fixture:
        metrics = [
            _fixture_metric("api.health.get", "api_route_smoke", [1.0, 1.2, 1.1]),
            _fixture_metric("api.status.get", "api_route_smoke", [1.7, 1.8, 1.9]),
            _fixture_metric("bind.classify", "bind_boundary", [0.2, 0.3, 0.2]),
            _fixture_metric("bind.validate_registry", "bind_boundary", [0.4, 0.4, 0.5]),
            _fixture_metric("bind.catalog_consistency", "bind_boundary", [0.3, 0.3, 0.3]),
            _fixture_metric(
                "trustlog.append.local",
                "trustlog_append",
                [0.9, 1.0, 1.1],
                "Measured with fixed-state local/test backend; per-sample log reset before append.",
            ),
            _fixture_metric(
                "decide.deterministic.fixture",
                "decide_deterministic",
                [2.1, 2.0, 2.2],
                "External LLM provider latency is excluded.",
            ),
        ]
        mode = "deterministic_fixture"
    else:
        from fastapi.testclient import TestClient
        from veritas_os.api.bind_target_catalog import CATALOG
        from veritas_os.api.server import app
        from veritas_os.policy.bind_coverage import classify_bind_coverage, validate_bind_coverage_registry

        client = TestClient(app)
        metrics = [
            measure_latency(
                "api.health.get",
                "api_route_smoke",
                lambda: _assert_status_ok(client.get("/v1/health")),
                sample_count,
                warmup_count,
                notes="expected HTTP 200",
            ),
            measure_latency(
                "api.status.get",
                "api_route_smoke",
                lambda: _assert_status_ok(client.get("/v1/status")),
                sample_count,
                warmup_count,
                notes="expected HTTP 200",
            ),
            measure_latency(
                "bind.classify",
                "bind_boundary",
                lambda: classify_bind_coverage("/v1/health", "GET"),
                sample_count,
                warmup_count,
            ),
            measure_latency(
                "bind.validate_registry",
                "bind_boundary",
                validate_bind_coverage_registry,
                sample_count,
                warmup_count,
            ),
            measure_latency(
                "bind.catalog_consistency",
                "bind_boundary",
                lambda: len({entry.target_path for entry in CATALOG}),
                sample_count,
                warmup_count,
            ),
            _measure_trustlog_append_fixed_state(sample_count, warmup_count),
            _fixture_metric(
                "decide.deterministic.fixture",
                "decide_deterministic",
                [2.1, 2.0, 2.2],
                "External LLM provider latency is excluded.",
            ),
        ]
        mode = "ci_safe_local"

    metrics = sorted(metrics, key=lambda item: (item["category"], item["name"]))
    for metric in metrics:
        if metric["status"] in {"failed", "not_measured"}:
            failures.append({"name": metric["name"], "error_type": metric["notes"]})

    status = "ok" if all(metric["status"] == "ok" for metric in metrics) else "partial"
    return {
        "schema_version": "performance_evidence.v1",
        "generated_at": _resolve_generated_at(generated_at),
        "environment": env,
        "measurement_mode": mode,
        "sample_count": sample_count,
        "warmup_count": warmup_count,
        "metrics": metrics,
        "failures": failures,
        "status": status,
        "interpretation_boundaries": [
            "This artifact is CI-safe local evidence, not a production SLA.",
            "This artifact does not include external LLM provider latency unless explicitly measured.",
            "This artifact does not include customer infrastructure latency.",
            "Results should be re-measured in customer PoC environments.",
            "TrustLog measurements use the configured local/test backend unless otherwise noted.",
        ],
    }


def render_performance_markdown(evidence: dict[str, Any]) -> str:
    """Render reviewer-readable markdown summary for performance evidence artifact."""

    lines = [
        "# Performance Evidence Artifact",
        "",
        "## Scope",
        "Reviewer-facing latency evidence for CI-safe local measurements.",
        "",
        "## Summary table",
        "| Metric | Value |",
        "| --- | --- |",
        f"| measurement_mode | {evidence['measurement_mode']} |",
        f"| sample_count | {evidence['sample_count']} |",
        f"| warmup_count | {evidence['warmup_count']} |",
        f"| status | {evidence['status']} |",
        "",
        "## Metrics table",
        "| Name | Category | p50 ms | p95 ms | p99 ms | Status | Notes |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for metric in evidence["metrics"]:
        lines.append(
            f"| {metric['name']} | {metric['category']} | {metric['p50_ms']:.3f} | "
            f"{metric['p95_ms']:.3f} | {metric['p99_ms']:.3f} | {metric['status']} | "
            f"{metric['notes']} |"
        )
    lines.extend(["", "## Failures / not measured"])
    if evidence["failures"]:
        for item in evidence["failures"]:
            lines.append(f"- {item['name']}: {item['error_type']}")
    else:
        lines.append("- None")
    lines.extend(
        ["", "## Interpretation boundaries"]
        + [f"- {boundary}" for boundary in evidence["interpretation_boundaries"]]
        + [
            "",
            "## How to regenerate",
            "```bash",
            "python -m scripts.performance.export_performance_evidence",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_performance_evidence(
    json_path: Path = OUTPUT_JSON,
    markdown_path: Path = OUTPUT_MD,
    generated_at: str | None = None,
    sample_count: int = 30,
    warmup_count: int = 3,
    deterministic_fixture: bool = False,
) -> dict[str, Any]:
    """Generate and persist JSON/Markdown performance evidence artifacts."""

    evidence = generate_performance_evidence(
        generated_at=generated_at,
        sample_count=sample_count,
        warmup_count=warmup_count,
        deterministic_fixture=deterministic_fixture,
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_performance_markdown(evidence).rstrip() + "\n",
        encoding="utf-8",
    )
    return evidence


def main() -> None:
    """CLI entrypoint for reviewer-facing evidence generation."""

    write_performance_evidence()


if __name__ == "__main__":
    main()
