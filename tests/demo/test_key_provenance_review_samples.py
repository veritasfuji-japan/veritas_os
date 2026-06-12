"""Validate illustrative Trusted Public Key Provenance review samples."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest


SAMPLE_DIR = Path("samples/evidence_bundle/key_provenance_review")
SCHEMA_CASES = [
    (
        "verification-result.json",
        Path("schemas/evidence_bundle_verification_result.schema.json"),
    ),
    (
        "trusted-public-key-provenance.json",
        Path("schemas/trusted_public_key_provenance_receipt.schema.json"),
    ),
    (
        "key-provenance-validation.json",
        Path(
            "schemas/"
            "trusted_public_key_provenance_validation_report.schema.json"
        ),
    ),
    (
        "key-provenance-result-validation.json",
        Path(
            "schemas/"
            "trusted_public_key_provenance_result_validation_report.schema.json"
        ),
    ),
    (
        "reviewer-evidence-packet.json",
        Path("docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"),
    ),
    (
        "reviewer-handoff-review-result.json",
        Path("schemas/reviewer_handoff_review_result.schema.json"),
    ),
    (
        "reviewer-review-result-validation.json",
        Path(
            "schemas/"
            "reviewer_handoff_review_result_validation_report.schema.json"
        ),
    ),
    (
        "reviewer-review-result-report-validation.json",
        Path(
            "schemas/"
            "reviewer_handoff_review_result_report_validation_report.schema.json"
        ),
    ),
    (
        "reviewer-handoff-package-validation.json",
        Path("schemas/reviewer_handoff_package_validation_report.schema.json"),
    ),
    (
        "reviewer-handoff-quickstart-command-validation.json",
        Path(
            "schemas/"
            "reviewer_handoff_quickstart_command_validation_report.schema.json"
        ),
    ),
    (
        "reviewer-handoff-quickstart-command-report-validation.json",
        Path(
            "schemas/"
            "reviewer_handoff_quickstart_command_report_validation_report.schema.json"
        ),
    ),
]
EXPECTED_CHAIN = [
    "verification-result.json",
    "trusted-public-key-provenance.json",
    "key-provenance-validation.json",
    "key-provenance-result-validation.json",
    "reviewer-evidence-packet.json",
    "reviewer-handoff-review-result.json",
    "reviewer-review-result-validation.json",
    "reviewer-review-result-report-validation.json",
    "reviewer-handoff-package-validation.json",
    "reviewer-handoff-quickstart-command-validation.json",
    "reviewer-handoff-quickstart-command-report-validation.json",
]
RAW_PRIVATE_KEY_PATTERNS = [
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
]
ABSOLUTE_LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:/(?:Users|home|tmp|var|workspace)/|[A-Za-z]:\\)"
)
EXCEPTION_TEXT_PATTERNS = [
    "Traceback (most recent call last)",
    "ValidationError",
    "jsonschema.exceptions",
    "FileNotFoundError",
    "PermissionError",
    "Exception:",
]
AJV_MODULE_PATH = Path("node_modules/.pnpm/ajv@6.14.0/node_modules/ajv")
SCHEMA_VALIDATOR_MESSAGE_PATTERNS = [
    "is not of type",
    "is a required property",
    "Additional properties are not allowed",
    "does not match",
    "Failed validating",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _validate_with_local_ajv(artifact_path: Path, schema_path: Path) -> None:
    if not AJV_MODULE_PATH.exists():
        pytest.skip("neither jsonschema nor local Ajv is available")

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
        ["node", "-e", script, str(schema_path), str(artifact_path)],
        check=True,
        text=True,
    )


def _sample_texts() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(SAMPLE_DIR.iterdir())
        if path.is_file()
    }


def test_key_provenance_review_sample_files_exist() -> None:
    assert SAMPLE_DIR.is_dir()
    for artifact_name in [*EXPECTED_CHAIN, "README.md"]:
        assert (SAMPLE_DIR / artifact_name).is_file()


@pytest.mark.parametrize(("artifact_name", "schema_path"), SCHEMA_CASES)
def test_key_provenance_review_samples_validate_against_schemas(
    artifact_name: str,
    schema_path: Path,
) -> None:
    artifact_path = SAMPLE_DIR / artifact_name
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        _validate_with_local_ajv(artifact_path, schema_path)
        return

    payload = _load_json(artifact_path)
    schema = _load_json(schema_path)

    jsonschema.Draft202012Validator(schema).validate(payload)


def test_key_provenance_review_sample_chain_is_referenced() -> None:
    packet = _load_json(SAMPLE_DIR / "reviewer-evidence-packet.json")
    key_provenance = packet["key_provenance"]

    assert key_provenance["trusted_public_key_provenance_receipt"] == {
        "artifact_name": "trusted-public-key-provenance.json",
        "required_for_strict_signature_review": True,
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_receipt.schema.json"
        ),
    }
    assert key_provenance["key_provenance_validation_report"] == {
        "artifact_name": "key-provenance-validation.json",
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_validation_report.schema.json"
        ),
    }
    assert key_provenance["key_provenance_result_validation_report"] == {
        "artifact_name": "key-provenance-result-validation.json",
        "schema_id": (
            "https://veritas-os.example/schemas/"
            "trusted_public_key_provenance_result_validation_report.schema.json"
        ),
    }

    readme = (SAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    chain_positions = [
        readme.index(artifact_name) for artifact_name in EXPECTED_CHAIN
    ]
    assert chain_positions == sorted(chain_positions)


def test_key_provenance_review_sample_fingerprints_correlate() -> None:
    verification_result = _load_json(SAMPLE_DIR / "verification-result.json")
    provenance_receipt = _load_json(
        SAMPLE_DIR / "trusted-public-key-provenance.json"
    )
    validation_report = _load_json(SAMPLE_DIR / "key-provenance-validation.json")

    assert verification_result["public_key_fingerprint_sha256"] == (
        provenance_receipt["public_key_fingerprint_sha256"]
    )
    assert validation_report["fingerprint_correlation_ok"] is True


def test_key_provenance_review_samples_have_clear_illustrative_boundaries() -> None:
    combined_text = "\n".join(_sample_texts().values())

    assert "Illustrative sample only" in combined_text
    assert "do not create trust" in combined_text
    assert "do not replace out-of-band public key trust" in combined_text
    assert "do not prove regulatory certification" in combined_text
    assert "not completed third-party audit approval" in combined_text
    assert "Matching fingerprints support correlation" in combined_text


@pytest.mark.parametrize("forbidden", RAW_PRIVATE_KEY_PATTERNS)
def test_key_provenance_review_samples_do_not_contain_raw_private_keys(
    forbidden: str,
) -> None:
    for name, text in _sample_texts().items():
        assert forbidden not in text, name


def test_key_provenance_review_samples_do_not_contain_absolute_local_paths() -> None:
    for name, text in _sample_texts().items():
        assert ABSOLUTE_LOCAL_PATH_PATTERN.search(text) is None, name


@pytest.mark.parametrize("forbidden", EXCEPTION_TEXT_PATTERNS)
def test_key_provenance_review_samples_do_not_contain_exception_text(
    forbidden: str,
) -> None:
    for name, text in _sample_texts().items():
        assert forbidden not in text, name


@pytest.mark.parametrize("forbidden", SCHEMA_VALIDATOR_MESSAGE_PATTERNS)
def test_key_provenance_review_samples_do_not_contain_schema_validator_messages(
    forbidden: str,
) -> None:
    for name, text in _sample_texts().items():
        assert forbidden not in text, name


def test_sample_fingerprints_are_synthetic_placeholders() -> None:
    verification_result = _load_json(SAMPLE_DIR / "verification-result.json")
    provenance_receipt = _load_json(
        SAMPLE_DIR / "trusted-public-key-provenance.json"
    )

    assert verification_result["public_key_fingerprint_sha256"] == "1" * 64
    assert provenance_receipt["public_key_fingerprint_sha256"] == "1" * 64


def test_forbidden_raw_sensitive_patterns_are_rejected() -> None:
    from scripts.quality import check_key_provenance_review_samples as gate

    representative_forbidden_text = {
        "raw private key": "-----BEGIN PRIVATE KEY-----",
        "real secret or credential": "api_key = livevalue12345",
        "absolute local path": "/home/example/secret.txt",
        "exception traceback or raw exception text": (
            "Traceback (most recent call last)"
        ),
        "raw schema validator message": "is a required property",
        "obvious production or customer data": "user@example.com",
        "raw external value outside sample placeholders": (
            "https://unexpected.example.net/value"
        ),
        "raw command stream dump": "stderr: sensitive output",
        "raw json value dump": "raw json payload",
    }

    for category, text in representative_forbidden_text.items():
        patterns = gate.SAFETY_PATTERNS[category]
        assert any(pattern.search(text) for pattern in patterns), category


@pytest.mark.parametrize(
    "doc_path",
    [
        Path("samples/evidence_bundle/key_provenance_review/README.md"),
        Path("docs/en/validation/reviewer-handoff-guide.md"),
        Path("docs/en/validation/reviewer-key-provenance-walkthrough.md"),
        Path("docs/en/validation/trusted-public-key-provenance.md"),
        Path("docs/en/validation/evidence-bundle-reviewer-checklist.md"),
        Path("README.md"),
        Path("README_JP.md"),
    ],
)
def test_requested_docs_link_key_provenance_review_sample(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "samples/evidence_bundle/key_provenance_review/" in text
    assert "reviewer-review-result-validation.json" in text
    assert "reviewer-review-result-report-validation.json" in text
    assert "reviewer-handoff-package-validation.json" in text


@pytest.mark.parametrize(
    "doc_path",
    [
        Path("samples/evidence_bundle/key_provenance_review/README.md"),
        Path("docs/en/validation/reviewer-handoff-sample-quickstart.md"),
        Path("docs/en/validation/reviewer-handoff-guide.md"),
        Path("docs/en/validation/reviewer-key-provenance-walkthrough.md"),
        Path("README.md"),
        Path("README_JP.md"),
    ],
)
def test_requested_docs_mention_quickstart_command_report_boundary(
    doc_path: Path,
) -> None:
    text = doc_path.read_text(encoding="utf-8")

    assert "reviewer-handoff-quickstart-command-validation.json" in text
    assert "trust source" in text or "trust を" in text
