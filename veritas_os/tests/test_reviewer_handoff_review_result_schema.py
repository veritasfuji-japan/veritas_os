"""Tests for reviewer handoff review-result artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from scripts.quality.check_key_provenance_review_samples import (
    _collect_safety_problems,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas/reviewer_handoff_review_result.schema.json"
SAMPLE_PATH = (
    REPO_ROOT
    / "samples/evidence_bundle/key_provenance_review/"
    "reviewer-handoff-review-result.json"
)
PACKAGE_VALIDATION_SCHEMA_PATH = (
    REPO_ROOT / "schemas/reviewer_handoff_package_validation_report.schema.json"
)
PACKAGE_VALIDATION_SAMPLE_PATH = (
    REPO_ROOT
    / "samples/evidence_bundle/key_provenance_review/"
    "reviewer-handoff-package-validation.json"
)
MANIFEST_PATH = (
    REPO_ROOT
    / "samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json"
)
VALIDATION_SCRIPT_PATH = (
    REPO_ROOT / "scripts/quality/check_key_provenance_review_samples.py"
)
DOC_PATHS = (
    REPO_ROOT / "docs/en/validation/reviewer-handoff-guide.md",
    REPO_ROOT / "docs/en/validation/reviewer-key-provenance-walkthrough.md",
    REPO_ROOT / "docs/en/validation/evidence-bundle-reviewer-checklist.md",
    REPO_ROOT / "docs/en/validation/trusted-public-key-provenance.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "README_JP.md",
)


FORBIDDEN_RAW_FINGERPRINT = "0123456789abcdef" * 4


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object fixture from the repository."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _validator() -> Draft202012Validator:
    """Return a Draft 2020-12 validator for review-result artifacts."""
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_review_result_schema_loads_as_draft_2020_12() -> None:
    """The reviewer result schema is a valid Draft 2020-12 schema."""
    schema = _load_json(SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False


def test_sample_reviewer_result_validates() -> None:
    """The illustrative reviewer result sample validates against its schema."""
    _validator().validate(_load_json(SAMPLE_PATH))


def test_reviewer_result_schema_rejects_forbidden_raw_sensitive_values() -> None:
    """Raw fingerprints and local paths are rejected from free-text fields."""
    payload = _load_json(SAMPLE_PATH)
    payload["notes"] = f"raw value {FORBIDDEN_RAW_FINGERPRINT}"

    fingerprint_errors = list(_validator().iter_errors(payload))

    assert fingerprint_errors

    payload = _load_json(SAMPLE_PATH)
    payload["reviewer"]["reviewer_id"] = "/home/reviewer/key.txt"

    local_path_errors = list(_validator().iter_errors(payload))

    assert local_path_errors


def test_manifest_includes_reviewer_result_with_matching_hash() -> None:
    """The sample manifest indexes the reviewer result and exact digest."""
    manifest = _load_json(MANIFEST_PATH)
    entries = {
        entry["artifact_name"]: entry for entry in manifest["artifacts"]
    }
    entry = entries["reviewer-handoff-review-result.json"]

    assert entry["role"] == "reviewer_handoff_review_result"
    assert (
        entry["schema_id"]
        == "https://veritas-os.example/schemas/"
        "reviewer_handoff_review_result.schema.json"
    )
    assert entry["sha256"] == hashlib.sha256(SAMPLE_PATH.read_bytes()).hexdigest()


def test_package_validation_report_sample_validates() -> None:
    """The package validation report sample matches its JSON Schema."""
    schema = _load_json(PACKAGE_VALIDATION_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)

    Draft202012Validator(schema).validate(
        _load_json(PACKAGE_VALIDATION_SAMPLE_PATH)
    )


def test_manifest_includes_package_validation_report_with_matching_hash() -> None:
    """The manifest indexes the package validation report and digest."""
    manifest = _load_json(MANIFEST_PATH)
    entries = {
        entry["artifact_name"]: entry for entry in manifest["artifacts"]
    }
    entry = entries["reviewer-handoff-package-validation.json"]

    assert entry["role"] == "reviewer_handoff_package_validation_report"
    assert (
        entry["schema_id"]
        == "https://veritas-os.example/schemas/"
        "reviewer_handoff_package_validation_report.schema.json"
    )
    assert entry["sha256"] == hashlib.sha256(
        PACKAGE_VALIDATION_SAMPLE_PATH.read_bytes()
    ).hexdigest()


def test_sample_validation_script_exits_zero() -> None:
    """The reviewer sample quality gate accepts the updated sample set."""
    completed = subprocess.run(
        [sys.executable, str(VALIDATION_SCRIPT_PATH)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_docs_link_to_reviewer_result_artifact_and_schema() -> None:
    """Reviewer-facing docs mention the review result and allowed decisions."""
    for doc_path in DOC_PATHS:
        text = doc_path.read_text(encoding="utf-8")

        assert "reviewer-handoff-review-result.json" in text
        assert "reviewer-handoff-package-validation.json" in text
        assert "ACCEPT" in text
        assert "REJECT" in text
        assert "NEEDS_FOLLOW_UP" in text


def test_sample_safety_gate_rejects_forbidden_raw_sensitive_patterns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The sample safety gate rejects raw public keys in checked artifacts."""
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "reviewer-handoff-review-result.json").write_text(
        "-----BEGIN PUBLIC KEY-----\nplaceholder\n-----END PUBLIC KEY-----\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.quality.check_key_provenance_review_samples.SAMPLE_DIR",
        sample_dir,
    )

    problems = _collect_safety_problems()

    assert any("forbidden raw external value" in problem.message for problem in problems)
