"""Tests for reviewer handoff sample regeneration checks."""

from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.quality.check_reviewer_handoff_sample_regeneration import (
    _canonical_json,
    _cli_command,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "samples/evidence_bundle/key_provenance_review"
REVIEW_RESULT_REPORT = "reviewer-review-result-validation.json"
REVIEW_RESULT_REPORT_VALIDATION = "reviewer-review-result-report-validation.json"
HANDOFF_PACKAGE_REPORT = "reviewer-handoff-package-validation.json"
QUICKSTART_COMMAND_REPORT_VALIDATION = (
    "reviewer-handoff-quickstart-command-report-validation.json"
)


def _copy_samples(tmp_path: Path) -> Path:
    """Copy reviewer handoff samples into a temporary editable directory."""
    sample_dir = tmp_path / "key_provenance_review"
    shutil.copytree(SAMPLE_DIR, sample_dir)
    return sample_dir


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from ``path`` for fixture mutation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic JSON matching the sample formatting style."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run_for_samples(sample_dir: Path) -> tuple[int, str]:
    """Run the checker against ``sample_dir`` and return code plus diagnostics."""
    stream = io.StringIO()
    code = run(sample_dir=sample_dir, stream=stream)
    return code, stream.getvalue()


def test_canonical_json_sorts_keys_for_stable_comparison(tmp_path: Path) -> None:
    """Canonical JSON comparison ignores object key order only."""
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text('{"validator":"x","ok":true}', encoding="utf-8")
    right.write_text('{"ok":true,"validator":"x"}', encoding="utf-8")

    assert _canonical_json(left) == _canonical_json(right)


def test_regeneration_checker_uses_module_cli_invocation() -> None:
    """The checker invokes the CLI through python -m for CI stability."""
    command = _cli_command(["validate-review-result", "--json"])

    assert command[:3] == [sys.executable, "-m", "veritas_os.cli.evidence_bundle"]
    assert command[3:] == ["validate-review-result", "--json"]


def test_regeneration_checker_accepts_committed_samples() -> None:
    """The current checked-in reviewer handoff reports regenerate cleanly."""
    code, output = _run_for_samples(SAMPLE_DIR)

    assert code == 0
    assert "PASS" in output


def test_regeneration_checker_rejects_modified_generated_field(
    tmp_path: Path,
) -> None:
    """Changing a generated diagnostics field causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT
    payload = _load_json(report_path)
    payload["errors"] = [{"check": "fixed", "path": "$", "message": "fixed"}]
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert "normalized_report_match" in output


def test_regeneration_checker_rejects_changed_validator(tmp_path: Path) -> None:
    """Changing validator metadata causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT
    payload = _load_json(report_path)
    payload["validator"] = "placeholder-validator"
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert REVIEW_RESULT_REPORT in output


def test_regeneration_checker_rejects_changed_report_schema_id(
    tmp_path: Path,
) -> None:
    """Changing report_schema_id metadata causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT_VALIDATION
    payload = _load_json(report_path)
    payload["report_schema_id"] = "https://veritas-os.example/schemas/changed.json"
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert REVIEW_RESULT_REPORT_VALIDATION in output


def test_regeneration_checker_rejects_changed_validated_schema_id(
    tmp_path: Path,
) -> None:
    """Changing validated_schema_id metadata causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT
    payload = _load_json(report_path)
    payload["validated_schema_id"] = "https://veritas-os.example/schemas/changed.json"
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert REVIEW_RESULT_REPORT in output


def test_regeneration_checker_rejects_changed_boolean_status(
    tmp_path: Path,
) -> None:
    """Changing boolean validation status causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / HANDOFF_PACKAGE_REPORT
    payload = _load_json(report_path)
    payload["ok"] = False
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert HANDOFF_PACKAGE_REPORT in output


def test_regeneration_checker_rejects_unknown_field(tmp_path: Path) -> None:
    """Adding an unexpected public output field causes regeneration failure."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT
    payload = _load_json(report_path)
    payload["unexpected_public_field"] = True
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert REVIEW_RESULT_REPORT in output



def test_regeneration_checker_rejects_quickstart_report_validation_drift(
    tmp_path: Path,
) -> None:
    """Changing the saved quickstart report validation sample is detected."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / QUICKSTART_COMMAND_REPORT_VALIDATION
    payload = _load_json(report_path)
    payload["ok"] = False
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    assert QUICKSTART_COMMAND_REPORT_VALIDATION in output
    assert "normalized_report_match" in output


def test_regeneration_checker_diagnostics_do_not_leak_raw_values(
    tmp_path: Path,
) -> None:
    """Failure diagnostics omit raw values, paths, fingerprints, and messages."""
    sample_dir = _copy_samples(tmp_path)
    report_path = sample_dir / REVIEW_RESULT_REPORT
    leak_markers = (
        "raw-json-value-customer-production-data",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "-----BEGIN PUBLIC KEY-----",
        "/tmp/veritas/local/absolute/path",
        "Traceback",
        "ValidationError",
        "schema validator says secret detail",
    )
    payload = _load_json(report_path)
    payload["validator"] = leak_markers[0]
    payload["errors"] = [
        {"check": "fixed", "path": "$", "message": marker}
        for marker in leak_markers[1:]
    ]
    _write_json(report_path, payload)

    code, output = _run_for_samples(sample_dir)

    assert code == 1
    for marker in leak_markers:
        assert marker not in output
    assert str(tmp_path) not in output
