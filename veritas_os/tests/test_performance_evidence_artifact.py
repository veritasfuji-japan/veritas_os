from __future__ import annotations

import json

import pytest

from scripts.performance.export_performance_evidence import (
    _assert_status_ok,
    generate_performance_evidence,
    measure_latency,
    percentile,
    render_performance_markdown,
    write_performance_evidence,
)


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "secret-token") -> None:
        self.status_code = status_code
        self.text = text


def test_generate_schema_and_fixed_timestamp() -> None:
    evidence = generate_performance_evidence(
        generated_at="1970-01-01T00:00:00Z",
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    assert evidence["schema_version"] == "performance_evidence.v1"
    assert evidence["generated_at"] == "1970-01-01T00:00:00Z"


@pytest.mark.parametrize("value", ["", "   ", "not-a-date"])
def test_generated_at_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        generate_performance_evidence(generated_at=value, deterministic_fixture=True)


@pytest.mark.parametrize(("pct", "expected"), [(0.0, 1.0), (1.0, 3.0), (0.5, 2.0)])
def test_percentile_valid(pct: float, expected: float) -> None:
    assert percentile([1.0, 2.0, 3.0], pct) == expected


@pytest.mark.parametrize("pct", [-0.1, 1.1])
def test_percentile_invalid_range(pct: float) -> None:
    with pytest.raises(ValueError):
        percentile([1.0, 2.0, 3.0], pct)


def test_assert_status_ok_raises_on_500() -> None:
    with pytest.raises(RuntimeError):
        _assert_status_ok(_FakeResponse(status_code=500))


def test_measure_latency_failed_sanitized_error_type_only() -> None:
    metric = measure_latency(
        "api.health.get",
        "api_route_smoke",
        lambda: _assert_status_ok(_FakeResponse(status_code=500, text="top-secret")),
        sample_count=2,
        warmup_count=0,
        notes="expected HTTP 200",
    )
    assert metric["status"] == "failed"
    assert "RuntimeError" in metric["notes"]
    assert "top-secret" not in metric["notes"]


def test_percentile_and_required_metric_fields() -> None:
    evidence = generate_performance_evidence(
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    assert isinstance(evidence["metrics"], list)
    assert evidence["sample_count"] == 3
    assert evidence["warmup_count"] == 0
    trustlog_metric = None
    for metric in evidence["metrics"]:
        assert "p50_ms" in metric
        assert "p95_ms" in metric
        assert "p99_ms" in metric
        assert "status" in metric
        if metric["name"] == "trustlog.append.local":
            trustlog_metric = metric
    assert trustlog_metric is not None
    assert (
        "fixed-state" in trustlog_metric["notes"]
        or "growing" in trustlog_metric["notes"]
    )


def test_markdown_and_writer_trailing_newline(tmp_path) -> None:
    json_path = tmp_path / "performance.json"
    md_path = tmp_path / "performance.md"
    evidence = write_performance_evidence(
        json_path,
        md_path,
        generated_at="1970-01-01T00:00:00+00:00",
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    rendered = render_performance_markdown(evidence)
    assert "## Summary table" in rendered
    assert "## Metrics table" in rendered
    assert "## Interpretation boundaries" in rendered
    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.endswith("\n")
    assert not md_text.endswith("\n\n")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["measurement_mode"] == "deterministic_fixture"
