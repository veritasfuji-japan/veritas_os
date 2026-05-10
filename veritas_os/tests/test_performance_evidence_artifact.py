from __future__ import annotations

import json

import pytest

from scripts.performance.export_performance_evidence import (
    generate_performance_evidence,
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
