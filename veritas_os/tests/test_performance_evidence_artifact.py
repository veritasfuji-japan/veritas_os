"""Tests for performance evidence exporter core."""

from scripts.performance.export_performance_evidence import (
    _HttpResult,
    _assert_http_status,
    export_performance_evidence,
    measure_latency,
    percentile,
    render_performance_markdown,
)


def test_schema_version_and_fixture_counts() -> None:
    payload = export_performance_evidence(deterministic_fixture=True)

    assert payload["schema_version"] == "performance_evidence.v1"
    assert payload["sample_count"] == 3
    assert payload["warmup_count"] == 0
    assert payload["measurement_mode"] == "deterministic_fixture"
    for metric in payload["metrics"]:
        assert len(metric["samples"]) == payload["sample_count"]


def test_generated_at_fixed_timestamp_reflected() -> None:
    payload = export_performance_evidence(
        deterministic_fixture=True,
        generated_at="1970-01-01T00:00:00+00:00",
    )
    assert payload["generated_at"] == "1970-01-01T00:00:00+00:00"

    payload_z = export_performance_evidence(
        deterministic_fixture=True,
        generated_at="1970-01-01T00:00:00Z",
    )
    assert payload_z["generated_at"] == "1970-01-01T00:00:00Z"


def test_invalid_generated_at_raises_value_error() -> None:
    for bad in ["", "   ", "not-a-date"]:
        try:
            export_performance_evidence(deterministic_fixture=True, generated_at=bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_percentile_boundaries_and_out_of_range() -> None:
    values = [1.0, 2.0, 3.0]
    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 1.0) == 3.0

    for bad in (-0.1, 1.1):
        try:
            percentile(values, bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_assert_http_status_validation() -> None:
    _assert_http_status(_HttpResult(status_code=200, body="ok"))

    try:
        _assert_http_status(_HttpResult(status_code=500, body="internal-error"))
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_measure_latency_converts_runtime_error_to_failed_metric() -> None:
    def fail() -> None:
        raise RuntimeError("raw-response-body=secret")

    metric = measure_latency("api_health", fail, sample_count=3)
    assert metric["status"] == "failed"
    assert "error_type=RuntimeError" in metric["notes"]
    assert "raw-response-body" not in metric["notes"]


def test_markdown_renderer_sections_and_trailing_newline() -> None:
    payload = export_performance_evidence(
        deterministic_fixture=True,
        generated_at="1970-01-01T00:00:00+00:00",
    )
    markdown = render_performance_markdown(payload)

    assert "## Summary table" in markdown
    assert "## Metrics table" in markdown
    assert "## Interpretation boundaries" in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")
