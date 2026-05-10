from __future__ import annotations

import json

from scripts.performance.check_performance_evidence_freshness import (
    FIXED_GENERATED_AT,
    REGENERATE_COMMAND,
    compare_performance_evidence,
    check_performance_evidence_freshness,
)
from scripts.performance.export_performance_evidence import write_performance_evidence


def test_freshness_ok(tmp_path) -> None:
    json_path = tmp_path / "performance-evidence.latest.json"
    md_path = tmp_path / "performance-evidence.latest.md"
    write_performance_evidence(
        json_path,
        md_path,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    assert check_performance_evidence_freshness(json_path, md_path) == 0


def test_freshness_fails_on_stale_schema(tmp_path) -> None:
    json_path = tmp_path / "performance-evidence.latest.json"
    md_path = tmp_path / "performance-evidence.latest.md"
    write_performance_evidence(
        json_path,
        md_path,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "stale"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert check_performance_evidence_freshness(json_path, md_path) == 1


def test_regenerate_command_constant() -> None:
    assert REGENERATE_COMMAND == "python -m scripts.performance.export_performance_evidence"


def test_compare_stale_when_generated_schema_mismatch(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(
        committed_json,
        committed_md,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    write_performance_evidence(
        generated_json,
        generated_md,
        generated_at=FIXED_GENERATED_AT,
        sample_count=3,
        warmup_count=0,
        deterministic_fixture=True,
    )
    payload = json.loads(generated_json.read_text(encoding="utf-8"))
    payload["schema_version"] = "performance_evidence.v2"
    generated_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert any("generated stale schema_version" in reason or "schema_version mismatch" in reason for reason in reasons)


def test_compare_stale_when_generated_at_invalid(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(committed_json, committed_md, generated_at=FIXED_GENERATED_AT, deterministic_fixture=True)
    write_performance_evidence(generated_json, generated_md, generated_at=FIXED_GENERATED_AT, deterministic_fixture=True)

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["generated_at"] = ""
    committed_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stale_files, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert str(committed_json) in stale_files
    assert any("invalid generated_at" in reason for reason in reasons)

    payload = json.loads(generated_json.read_text(encoding="utf-8"))
    payload["generated_at"] = "not-a-date"
    generated_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stale_files, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert stale_files == [str(committed_json)]
    assert any("generated artifact invalid generated_at" in reason for reason in reasons)


def test_missing_committed_json_returns_stale_without_traceback(tmp_path, capsys) -> None:
    committed_json = tmp_path / "missing.json"
    committed_md = tmp_path / "committed.md"
    write_performance_evidence(committed_md.with_suffix(".json"), committed_md, deterministic_fixture=True)
    result = check_performance_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out
    assert result == 1
    assert "failed to read JSON" in output
    assert REGENERATE_COMMAND in output
    assert "Traceback" not in output


def test_invalid_committed_json_returns_stale_without_traceback(tmp_path, capsys) -> None:
    committed_json = tmp_path / "invalid.json"
    committed_md = tmp_path / "committed.md"
    write_performance_evidence(committed_json, committed_md, deterministic_fixture=True)
    committed_json.write_text("{invalid", encoding="utf-8")
    result = check_performance_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out
    assert result == 1
    assert "failed to read JSON" in output
    assert "Traceback" not in output


def test_non_dict_committed_json_is_stale(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(generated_json, generated_md, deterministic_fixture=True)
    committed_json.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    committed_md.write_text(generated_md.read_text(encoding="utf-8"), encoding="utf-8")
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert str(committed_json) in stale_files
    assert any("JSON payload must be an object" in reason for reason in reasons)


def test_generated_json_missing_maps_to_committed_path(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "missing-generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(committed_json, committed_md, deterministic_fixture=True)
    write_performance_evidence(tmp_path / "tmp.json", generated_md, deterministic_fixture=True)
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert stale_files == [str(committed_json), str(committed_md)] or str(committed_json) in stale_files
    assert str(generated_json) not in stale_files
    assert any("failed to generate JSON artifact" in reason for reason in reasons)


def test_committed_md_missing_returns_stale_without_traceback(tmp_path, capsys) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "missing.md"
    write_performance_evidence(committed_json, tmp_path / "other.md", deterministic_fixture=True)
    result = check_performance_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out
    assert result == 1
    assert "failed to read markdown" in output
    assert "Traceback" not in output


def test_generated_md_missing_maps_to_committed_path(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "missing-generated.md"
    write_performance_evidence(committed_json, committed_md, deterministic_fixture=True)
    write_performance_evidence(generated_json, tmp_path / "other.md", deterministic_fixture=True)
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert str(committed_md) in stale_files
    assert str(generated_md) not in stale_files
    assert any("failed to generate markdown artifact" in reason for reason in reasons)


def test_json_content_drift_detection_and_normalized_fields(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(
        committed_json,
        committed_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )
    write_performance_evidence(
        generated_json,
        generated_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )

    committed_payload = json.loads(committed_json.read_text(encoding="utf-8"))
    committed_payload["generated_at"] = "2000-01-01T00:00:00+00:00"
    committed_payload["environment"] = {
        "python_version": "x",
        "platform": "y",
        "implementation": "z",
        "ci_detected": True,
    }
    committed_json.write_text(
        json.dumps(committed_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert stale_files == []
    assert not any("content differs from regenerated artifact" in reason for reason in reasons)

    drift_payload = json.loads(committed_json.read_text(encoding="utf-8"))
    drift_payload["sample_count"] = 99
    drift_payload["metrics"][0]["p50_ms"] = 999.0
    drift_payload["metrics"][0]["samples"] = [999.0, 999.0, 999.0]
    drift_payload["metrics"][0]["notes"] = "drifted"
    committed_json.write_text(
        json.dumps(drift_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert str(committed_json) in stale_files
    assert any("content differs from regenerated artifact" in reason for reason in reasons)


def test_missing_environment_is_stale(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(
        committed_json,
        committed_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )
    write_performance_evidence(
        generated_json,
        generated_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )
    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload.pop("environment", None)
    committed_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    stale_files, reasons = compare_performance_evidence(
        committed_json,
        committed_md,
        generated_json,
        generated_md,
    )
    assert str(committed_json) in stale_files
    assert any("missing required field environment" in reason for reason in reasons)


def test_invalid_utf8_json_is_stale_without_traceback(tmp_path, capsys) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    write_performance_evidence(committed_json, committed_md, deterministic_fixture=True)
    committed_json.write_bytes(b"\xff\xfe\x00")
    result = check_performance_evidence_freshness(committed_json, committed_md)
    output = capsys.readouterr().out
    assert result == 1
    assert "UnicodeDecodeError" in output or "failed to read JSON" in output
    assert REGENERATE_COMMAND in output
    assert "Traceback" not in output


def test_environment_structure_validation(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(
        committed_json,
        committed_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )
    write_performance_evidence(
        generated_json,
        generated_md,
        generated_at=FIXED_GENERATED_AT,
        deterministic_fixture=True,
    )

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["environment"] = []
    committed_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert any("environment must be an object" in reason for reason in reasons)

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["environment"] = {
        "platform": "x",
        "implementation": "y",
        "ci_detected": False,
    }
    committed_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert any("environment missing python_version" in reason for reason in reasons)

    payload = json.loads(committed_json.read_text(encoding="utf-8"))
    payload["environment"]["python_version"] = "3.12"
    payload["environment"]["ci_detected"] = "false"
    committed_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert any("environment ci_detected must be bool" in reason for reason in reasons)


def test_generated_environment_invalid_maps_to_committed_path(tmp_path) -> None:
    committed_json = tmp_path / "committed.json"
    committed_md = tmp_path / "committed.md"
    generated_json = tmp_path / "generated.json"
    generated_md = tmp_path / "generated.md"
    write_performance_evidence(committed_json, committed_md, deterministic_fixture=True)
    write_performance_evidence(generated_json, generated_md, deterministic_fixture=True)
    payload = json.loads(generated_json.read_text(encoding="utf-8"))
    payload["environment"] = []
    generated_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    stale_files, reasons = compare_performance_evidence(committed_json, committed_md, generated_json, generated_md)
    assert stale_files == [str(committed_json)]
    assert any("environment must be an object" in reason for reason in reasons)
