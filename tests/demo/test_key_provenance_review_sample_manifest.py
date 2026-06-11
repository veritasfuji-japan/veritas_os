"""Validate the Trusted Public Key Provenance review sample manifest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


SAMPLE_DIR = Path("samples/evidence_bundle/key_provenance_review")
MANIFEST_PATH = SAMPLE_DIR / "sample-artifact-manifest.json"
MANIFEST_SCHEMA_PATH = Path(
    "schemas/trusted_public_key_provenance_review_sample_manifest.schema.json"
)
AJV_MODULE_PATH = Path("node_modules/.pnpm/ajv@6.14.0/node_modules/ajv")
EXPECTED_ARTIFACTS = (
    "verification-result.json",
    "trusted-public-key-provenance.json",
    "key-provenance-validation.json",
    "key-provenance-result-validation.json",
    "reviewer-evidence-packet.json",
    "reviewer-handoff-review-result.json",
    "reviewer-review-result-validation.json",
    "reviewer-review-result-report-validation.json",
    "reviewer-handoff-package-validation.json",
    "README.md",
)
EXPECTED_ROLES = {
    "verification-result.json": "strict_evidence_bundle_verification_result",
    "trusted-public-key-provenance.json": "trusted_public_key_provenance_receipt",
    "key-provenance-validation.json": "key_provenance_validation_report",
    "key-provenance-result-validation.json": (
        "key_provenance_result_validation_report"
    ),
    "reviewer-evidence-packet.json": "reviewer_evidence_packet",
    "reviewer-handoff-review-result.json": "reviewer_handoff_review_result",
    "reviewer-review-result-validation.json": (
        "reviewer_handoff_review_result_validation_report"
    ),
    "reviewer-review-result-report-validation.json": (
        "reviewer_handoff_review_result_report_validation_report"
    ),
    "reviewer-handoff-package-validation.json": (
        "reviewer_handoff_package_validation_report"
    ),
    "README.md": "sample_readme",
}
EXPECTED_SCHEMA_IDS = {
    "verification-result.json": (
        "https://veritas-os.example/schemas/"
        "evidence_bundle_verification_result.schema.json"
    ),
    "trusted-public-key-provenance.json": (
        "https://veritas-os.example/schemas/"
        "trusted_public_key_provenance_receipt.schema.json"
    ),
    "key-provenance-validation.json": (
        "https://veritas-os.example/schemas/"
        "trusted_public_key_provenance_validation_report.schema.json"
    ),
    "key-provenance-result-validation.json": (
        "https://veritas-os.example/schemas/"
        "trusted_public_key_provenance_result_validation_report.schema.json"
    ),
    "reviewer-evidence-packet.json": (
        "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
    ),
    "reviewer-handoff-review-result.json": (
        "https://veritas-os.example/schemas/"
        "reviewer_handoff_review_result.schema.json"
    ),
    "reviewer-review-result-validation.json": (
        "https://veritas-os.example/schemas/"
        "reviewer_handoff_review_result_validation_report.schema.json"
    ),
    "reviewer-review-result-report-validation.json": (
        "https://veritas-os.example/schemas/"
        "reviewer_handoff_review_result_report_validation_report.schema.json"
    ),
    "reviewer-handoff-package-validation.json": (
        "https://veritas-os.example/schemas/"
        "reviewer_handoff_package_validation_report.schema.json"
    ),
    "README.md": None,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_with_local_ajv(payload: dict[str, Any], tmp_path: Path) -> None:
    if not AJV_MODULE_PATH.exists():
        pytest.fail("neither jsonschema nor local Ajv is available")

    payload_path = tmp_path / "manifest-under-test.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    script = """
const fs = require('fs');
const Ajv = require('./node_modules/.pnpm/ajv@6.14.0/node_modules/ajv');
const schema = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
delete schema.$schema;
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ajv = new Ajv({
  allErrors: true,
  meta: false,
  schemaId: 'auto',
  unknownFormats: 'ignore',
  validateSchema: false,
});
const validate = ajv.compile(schema);
if (!validate(data)) {
  process.stderr.write(JSON.stringify(validate.errors));
  process.exit(1);
}
"""
    subprocess.run(
        ["node", "-e", script, str(MANIFEST_SCHEMA_PATH), str(payload_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _validate_manifest(payload: dict[str, Any], tmp_path: Path) -> None:
    if importlib.util.find_spec("jsonschema") is None:
        _validate_with_local_ajv(payload, tmp_path)
        return

    import jsonschema

    schema = _load_json(MANIFEST_SCHEMA_PATH)
    jsonschema.Draft202012Validator(schema).validate(payload)


def _validation_error_types() -> tuple[type[BaseException], ...]:
    if importlib.util.find_spec("jsonschema") is None:
        return (subprocess.CalledProcessError,)

    import jsonschema

    return (jsonschema.ValidationError,)


def _manifest() -> dict[str, Any]:
    return _load_json(MANIFEST_PATH)


def _artifact_entries() -> dict[str, dict[str, Any]]:
    return {
        artifact["artifact_name"]: artifact
        for artifact in _manifest()["artifacts"]
    }


def test_manifest_validates_against_schema(tmp_path: Path) -> None:
    _validate_manifest(_manifest(), tmp_path)


def test_manifest_lists_all_expected_sample_artifacts() -> None:
    entries = _artifact_entries()

    assert tuple(entries) == EXPECTED_ARTIFACTS
    assert {name: entry["role"] for name, entry in entries.items()} == EXPECTED_ROLES
    assert {
        name: entry["schema_id"] for name, entry in entries.items()
    } == EXPECTED_SCHEMA_IDS


def test_manifest_sha256_digests_match_actual_files() -> None:
    for artifact_name, entry in _artifact_entries().items():
        artifact_path = SAMPLE_DIR / artifact_name
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        assert entry["sha256"] == digest


def test_manifest_rejects_unknown_artifact_names(tmp_path: Path) -> None:
    manifest = deepcopy(_manifest())
    manifest["artifacts"][0]["artifact_name"] = "unexpected.json"

    with pytest.raises(_validation_error_types()):
        _validate_manifest(manifest, tmp_path)


def test_manifest_rejects_unknown_roles(tmp_path: Path) -> None:
    manifest = deepcopy(_manifest())
    manifest["artifacts"][0]["role"] = "unexpected_role"

    with pytest.raises(_validation_error_types()):
        _validate_manifest(manifest, tmp_path)


def test_manifest_rejects_unexpected_schema_ids(tmp_path: Path) -> None:
    manifest = deepcopy(_manifest())
    manifest["artifacts"][0]["schema_id"] = (
        "https://veritas-os.example/schemas/unexpected.schema.json"
    )

    with pytest.raises(_validation_error_types()):
        _validate_manifest(manifest, tmp_path)


def test_manifest_contains_sample_only_non_certification_boundary_language() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")

    assert "Illustrative sample only" in manifest_text
    assert "Not production evidence" in manifest_text
    assert "not regulatory certification" in manifest_text
    assert "not completed third-party audit approval" in manifest_text
    assert "does not create trust" in manifest_text
    assert "does not replace out-of-band public key trust" in manifest_text


def test_key_provenance_review_samples_ci_gate_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/quality/check_key_provenance_review_samples.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
