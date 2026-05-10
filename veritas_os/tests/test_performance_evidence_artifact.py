from __future__ import annotations

import json

import pytest

from scripts.performance.export_performance_evidence import (
    _assert_http_status,
    generate_performance_evidence,
    measure_latency,
    percentile,
    render_performance_markdown,
    write_performance_evidence,
)


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


def test_percentile_and_required_metric_fields() -> None:
    assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    evidence = generate_performance_evidence(sample_count=3, warmup_count=0, deterministic_fixture=True)
    assert isinstance(evidence["metrics"], list)
    assert evidence["sample_count"] == 3
    assert evidence["warmup_count"] == 0
    for metric in evidence["metrics"]:
        assert "p50_ms" in metric
        assert "p95_ms" in metric
        assert "p99_ms" in metric
        assert "status" in metric


def test_deterministic_fixture_normalizes_sampling() -> None:
    evidence = generate_performance_evidence(
        sample_count=30,
        warmup_count=5,
        deterministic_fixture=True,
    )
    assert evidence["sample_count"] == 3
    assert evidence["warmup_count"] == 0
    assert all(len(metric["samples"]) == 3 for metric in evidence["metrics"])


def test_non_fixture_sampling_knobs_are_kept() -> None:
    evidence = generate_performance_evidence(
        sample_count=5,
        warmup_count=1,
        deterministic_fixture=False,
    )
    assert evidence["sample_count"] == 5
    assert evidence["warmup_count"] == 1


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
    assert "| Metric | Value |" in rendered
    assert "|| Metric | Value |" not in rendered
    assert "## Metrics table" in rendered
    assert "## Interpretation boundaries" in rendered
    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.endswith("\n")
    assert not md_text.endswith("\n\n")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["measurement_mode"] == "deterministic_fixture"


def test_assert_http_status_helper() -> None:
    class Response:
        def __init__(self, status_code: int, text: str = "") -> None:
            self.status_code = status_code
            self.text = text

    ok = Response(200, "ok")
    assert _assert_http_status(ok) is ok
    with pytest.raises(RuntimeError):
        _assert_http_status(Response(500, "secret-body"))


def test_measure_latency_failed_status_hides_response_body() -> None:
    class Response:
        status_code = 500
        text = "sensitive-payload"

    metric = measure_latency(
        "api.health.get",
        "api_route_smoke",
        lambda: _assert_http_status(Response()),
        sample_count=1,
        warmup_count=0,
    )
    assert metric["status"] == "failed"
    assert "error_type=RuntimeError" in metric["notes"]
    assert "sensitive-payload" not in metric["notes"]
