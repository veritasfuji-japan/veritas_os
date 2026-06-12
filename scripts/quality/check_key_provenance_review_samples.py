#!/usr/bin/env python3
"""Validate Trusted Public Key Provenance reviewer sample artifacts.

The samples under ``samples/evidence_bundle/key_provenance_review`` are
illustrative reviewer-facing artifacts. This gate keeps that sample chain
schema-valid, internally linked, and free of obvious sensitive/raw diagnostic
content that would be unsafe to copy into public documentation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "samples/evidence_bundle/key_provenance_review"
WALKTHROUGH_PATH = (
    REPO_ROOT / "docs/en/validation/reviewer-key-provenance-walkthrough.md"
)
AJV_MODULE_PATH = REPO_ROOT / "node_modules/.pnpm/ajv@6.14.0/node_modules/ajv"
MANIFEST_NAME = "sample-artifact-manifest.json"
MANIFEST_PATH = SAMPLE_DIR / MANIFEST_NAME
MANIFEST_SCHEMA_PATH = (
    REPO_ROOT
    / "schemas/trusted_public_key_provenance_review_sample_manifest.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_REVIEW_SAMPLE_MANIFEST_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_review_sample_manifest.schema.json"
)

EVIDENCE_BUNDLE_VERIFICATION_RESULT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "evidence_bundle_verification_result.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_receipt.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_validation_report.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "trusted_public_key_provenance_result_validation_report.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_review_result.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_review_result_validation_report.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_review_result_report_validation_report.schema.json"
)
REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_package_validation_report.schema.json"
)
REVIEWER_HANDOFF_QUICKSTART_COMMAND_VALIDATION_REPORT_SCHEMA_ID = (
    "https://veritas-os.example/schemas/"
    "reviewer_handoff_quickstart_command_validation_report.schema.json"
)
VALIDATE_REVIEW_RESULT_VALIDATOR = (
    "veritas-evidence-bundle validate-review-result"
)
VALIDATE_REVIEW_RESULT_REPORT_VALIDATOR = (
    "veritas-evidence-bundle validate-review-result-report"
)
VALIDATE_REVIEWER_HANDOFF_PACKAGE_VALIDATOR = (
    "veritas-evidence-bundle validate-reviewer-handoff-package"
)
QUICKSTART_COMMAND_VALIDATOR = (
    "scripts/quality/check_reviewer_handoff_quickstart_command.py"
)

SAMPLE_SCHEMA_CASES = {
    "verification-result.json": (
        REPO_ROOT / "schemas/evidence_bundle_verification_result.schema.json"
    ),
    "trusted-public-key-provenance.json": (
        REPO_ROOT / "schemas/trusted_public_key_provenance_receipt.schema.json"
    ),
    "key-provenance-validation.json": (
        REPO_ROOT
        / "schemas/trusted_public_key_provenance_validation_report.schema.json"
    ),
    "key-provenance-result-validation.json": (
        REPO_ROOT
        / "schemas/"
        "trusted_public_key_provenance_result_validation_report.schema.json"
    ),
    "reviewer-evidence-packet.json": (
        REPO_ROOT
        / "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
    ),
    "reviewer-handoff-review-result.json": (
        REPO_ROOT / "schemas/reviewer_handoff_review_result.schema.json"
    ),
    "reviewer-review-result-validation.json": (
        REPO_ROOT
        / "schemas/reviewer_handoff_review_result_validation_report.schema.json"
    ),
    "reviewer-review-result-report-validation.json": (
        REPO_ROOT
        / "schemas/"
        "reviewer_handoff_review_result_report_validation_report.schema.json"
    ),
    "reviewer-handoff-package-validation.json": (
        REPO_ROOT
        / "schemas/reviewer_handoff_package_validation_report.schema.json"
    ),
    "reviewer-handoff-quickstart-command-validation.json": (
        REPO_ROOT
        / "schemas/"
        "reviewer_handoff_quickstart_command_validation_report.schema.json"
    ),
    MANIFEST_NAME: MANIFEST_SCHEMA_PATH,
}

EXPECTED_ARTIFACT_CHAIN = (
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
)
EXPECTED_MANIFEST_ARTIFACTS = (*EXPECTED_ARTIFACT_CHAIN, "README.md")
EXPECTED_MANIFEST_ENTRIES = {
    "verification-result.json": {
        "role": "strict_evidence_bundle_verification_result",
        "schema_id": EVIDENCE_BUNDLE_VERIFICATION_RESULT_SCHEMA_ID,
    },
    "trusted-public-key-provenance.json": {
        "role": "trusted_public_key_provenance_receipt",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID,
    },
    "key-provenance-validation.json": {
        "role": "key_provenance_validation_report",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID,
    },
    "key-provenance-result-validation.json": {
        "role": "key_provenance_result_validation_report",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID,
    },
    "reviewer-evidence-packet.json": {
        "role": "reviewer_evidence_packet",
        "schema_id": "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json",
    },
    "reviewer-handoff-review-result.json": {
        "role": "reviewer_handoff_review_result",
        "schema_id": REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID,
    },
    "reviewer-review-result-validation.json": {
        "role": "reviewer_handoff_review_result_validation_report",
        "schema_id": REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID,
    },
    "reviewer-review-result-report-validation.json": {
        "role": "reviewer_handoff_review_result_report_validation_report",
        "schema_id": (
            REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID
        ),
    },
    "reviewer-handoff-package-validation.json": {
        "role": "reviewer_handoff_package_validation_report",
        "schema_id": REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID,
    },
    "reviewer-handoff-quickstart-command-validation.json": {
        "role": "quickstart_command_validation_report",
        "schema_id": (
            REVIEWER_HANDOFF_QUICKSTART_COMMAND_VALIDATION_REPORT_SCHEMA_ID
        ),
        "validator": QUICKSTART_COMMAND_VALIDATOR,
    },
    "README.md": {"role": "sample_readme", "schema_id": None},
}

REQUIRED_REVIEW_RESULT_LIMITATIONS = (
    "does_not_create_trust",
    "does_not_replace_out_of_band_public_key_trust",
    "not_regulatory_certification",
    "not_completed_third_party_audit_approval",
    "fingerprint_matching_is_correlation_not_standalone_trust",
    "sample_hashes_support_sample_integrity_only",
)

EXPECTED_KEY_PROVENANCE_REFERENCES = {
    "trusted_public_key_provenance_receipt": {
        "artifact_name": "trusted-public-key-provenance.json",
        "required_for_strict_signature_review": True,
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID,
    },
    "key_provenance_validation_report": {
        "artifact_name": "key-provenance-validation.json",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID,
    },
    "key_provenance_result_validation_report": {
        "artifact_name": "key-provenance-result-validation.json",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID,
    },
}

SAFETY_PATTERNS = {
    "raw private key": (
        re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
        re.compile(r"-----BEGIN ENCRYPTED PRIVATE KEY-----"),
    ),
    "real secret or credential": (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"ASIA[0-9A-Z]{16}"),
        re.compile(r"sk_live_[0-9A-Za-z]{12,}"),
        re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
        re.compile(r"ghp_[0-9A-Za-z]{20,}"),
        re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret)\b"
            r"\s*[:=]\s*['\"]?(?!sample|example|placeholder|synthetic)"
            r"[A-Za-z0-9_./+=-]{8,}"
        ),
    ),
    "absolute local path": (
        re.compile(r"(?<![A-Za-z0-9])(?:/(?:Users|home|tmp|var|workspace)/)"),
        re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\"),
    ),
    "exception traceback or raw exception text": (
        re.compile(r"Traceback \(most recent call last\)"),
        re.compile(r"\b(?:FileNotFoundError|PermissionError|RuntimeError):"),
        re.compile(r"\b(?:Exception|ValidationError):"),
        re.compile(r"jsonschema\.exceptions"),
    ),
    "raw schema validator message": (
        re.compile(r"\bis not of type\b"),
        re.compile(r"\bis a required property\b"),
        re.compile(r"Additional properties are not allowed"),
        re.compile(r"Failed validating"),
        re.compile(r"\bdoes not match\b"),
    ),
    "obvious production or customer data": (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        re.compile(r"\bcustomer[_ -]?(?!data\b)[A-Za-z0-9-]{4,}\b", re.I),
    ),
    "raw external value outside sample placeholders": (
        re.compile(r"https?://(?!veritas-os\.(?:example|local)\b)[^\s\"')]+"),
        re.compile(r"-----BEGIN PUBLIC KEY-----"),
        re.compile(r"-----BEGIN CERTIFICATE-----"),
    ),
    "raw command stream dump": (
        re.compile(r"(?im)^\s*(?:stdout|stderr)\s*[:=]"),
        re.compile(r"(?i)raw command (?:stdout|stderr|output)"),
    ),
    "raw json value dump": (
        re.compile(r"(?i)raw json (?:value|payload|dump)"),
    ),
}

BOUNDARY_PHRASES = (
    "Illustrative sample only",
    "do not create trust",
    "do not replace out-of-band public key trust",
    "do not prove regulatory certification",
    "not completed third-party audit approval",
    "Matching fingerprints support correlation",
)


class ValidationProblem:
    """A deterministic validation problem with path-oriented diagnostics."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message

    def format(self) -> str:
        """Return a repository-relative diagnostic string."""
        try:
            path_label = str(self.path.relative_to(REPO_ROOT))
        except ValueError:
            path_label = str(self.path)
        return f"{path_label}: {self.message}"


def _load_json(path: Path) -> Any:
    """Load JSON from ``path`` and let callers convert errors to diagnostics."""
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_id(schema_path: Path) -> str:
    """Return the declared JSON Schema identifier for ``schema_path``."""
    schema = _load_json(schema_path)
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str):
        return ""
    return schema_id


def _jsonschema_module() -> Any | None:
    """Return the jsonschema module when available in the runtime."""
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _validate_with_local_ajv(artifact_path: Path, schema_path: Path) -> None:
    """Validate with the repository-local Ajv dependency as a fallback."""
    if not AJV_MODULE_PATH.exists():
        raise RuntimeError("neither jsonschema nor repository-local Ajv is available")

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
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _validate_against_schema(artifact_path: Path, schema_path: Path) -> None:
    """Validate an artifact with jsonschema or the local Ajv fallback."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        _validate_with_local_ajv(artifact_path, schema_path)
        return

    payload = _load_json(artifact_path)
    schema = _load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(payload)


def _iter_sample_texts() -> Iterable[tuple[Path, str]]:
    """Yield text for all checked sample artifacts, including README context."""
    for path in sorted(SAMPLE_DIR.iterdir()):
        if path.is_file() and path.suffix in {".json", ".md"}:
            yield path, path.read_text(encoding="utf-8")


def _collect_file_and_schema_problems() -> list[ValidationProblem]:
    """Validate required files and JSON sample artifacts against schemas."""
    problems: list[ValidationProblem] = []
    if not SAMPLE_DIR.is_dir():
        return [ValidationProblem(SAMPLE_DIR, "sample directory is missing")]

    for artifact_name, schema_path in SAMPLE_SCHEMA_CASES.items():
        artifact_path = SAMPLE_DIR / artifact_name
        if not artifact_path.is_file():
            problems.append(ValidationProblem(artifact_path, "sample file is missing"))
            continue
        if not schema_path.is_file():
            problems.append(ValidationProblem(schema_path, "schema file is missing"))
            continue

        try:
            _validate_against_schema(artifact_path, schema_path)
        except (
            json.JSONDecodeError,
            RuntimeError,
            subprocess.CalledProcessError,
        ) as exc:
            problems.append(
                ValidationProblem(
                    artifact_path,
                    "does not validate against "
                    f"{schema_path.relative_to(REPO_ROOT)}: {exc}",
                )
            )
        except Exception as exc:  # jsonschema.ValidationError or SchemaError.
            message = getattr(exc, "message", str(exc))
            problems.append(
                ValidationProblem(
                    artifact_path,
                    "does not validate against "
                    f"{schema_path.relative_to(REPO_ROOT)}: {message}",
                )
            )
    return problems


def _sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a sample artifact file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_manifest_problems() -> list[ValidationProblem]:
    """Validate manifest completeness, schema ids, and artifact digests."""
    problems: list[ValidationProblem] = []
    if not MANIFEST_PATH.is_file():
        return [ValidationProblem(MANIFEST_PATH, "manifest file is missing")]

    try:
        manifest = _load_json(MANIFEST_PATH)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [ValidationProblem(MANIFEST_PATH, f"cannot load manifest: {exc}")]

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return [ValidationProblem(MANIFEST_PATH, "manifest artifacts must be a list")]

    entries_by_name: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            problems.append(
                ValidationProblem(MANIFEST_PATH, f"artifact entry {index} is invalid")
            )
            continue
        artifact_name = entry.get("artifact_name")
        if not isinstance(artifact_name, str):
            problems.append(
                ValidationProblem(
                    MANIFEST_PATH,
                    f"artifact entry {index} has invalid artifact_name",
                )
            )
            continue
        if artifact_name in entries_by_name:
            problems.append(
                ValidationProblem(MANIFEST_PATH, f"duplicate artifact {artifact_name}")
            )
        entries_by_name[artifact_name] = entry

    listed_names = tuple(entries_by_name)
    if listed_names != EXPECTED_MANIFEST_ARTIFACTS:
        problems.append(
            ValidationProblem(
                MANIFEST_PATH,
                "artifact names do not match the reviewer walkthrough sample set",
            )
        )

    missing = set(EXPECTED_MANIFEST_ARTIFACTS) - set(entries_by_name)
    unexpected = set(entries_by_name) - set(EXPECTED_MANIFEST_ARTIFACTS)
    if missing:
        problems.append(
            ValidationProblem(
                MANIFEST_PATH,
                "missing expected artifacts: " + ", ".join(sorted(missing)),
            )
        )
    if unexpected:
        problems.append(
            ValidationProblem(
                MANIFEST_PATH,
                "unexpected artifacts: " + ", ".join(sorted(unexpected)),
            )
        )

    for artifact_name, expected in EXPECTED_MANIFEST_ENTRIES.items():
        entry = entries_by_name.get(artifact_name)
        artifact_path = SAMPLE_DIR / artifact_name
        if not artifact_path.is_file():
            problems.append(
                ValidationProblem(artifact_path, "listed artifact is missing")
            )
            continue
        if entry is None:
            continue
        if entry.get("role") != expected["role"]:
            problems.append(
                ValidationProblem(MANIFEST_PATH, f"unexpected role for {artifact_name}")
            )
        if entry.get("schema_id") != expected["schema_id"]:
            problems.append(
                ValidationProblem(
                    MANIFEST_PATH,
                    f"unexpected schema_id for {artifact_name}",
                )
            )
        expected_validator = expected.get("validator")
        if expected_validator is None:
            if "validator" in entry:
                problems.append(
                    ValidationProblem(
                        MANIFEST_PATH,
                        f"unexpected validator for {artifact_name}",
                    )
                )
        elif entry.get("validator") != expected_validator:
            problems.append(
                ValidationProblem(
                    MANIFEST_PATH,
                    f"unexpected validator for {artifact_name}",
                )
            )
        if entry.get("sha256") != _sha256(artifact_path):
            problems.append(
                ValidationProblem(MANIFEST_PATH, f"sha256 mismatch for {artifact_name}")
            )

    return problems


def _collect_safety_problems() -> list[ValidationProblem]:
    """Block private keys, secrets, local paths, raw errors, and customer data."""
    problems: list[ValidationProblem] = []
    for path, text in _iter_sample_texts():
        for category, patterns in SAFETY_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(text):
                    problems.append(
                        ValidationProblem(path, f"contains forbidden {category}")
                    )
                    break
    return problems


def _collect_boundary_problems() -> list[ValidationProblem]:
    """Ensure samples keep precise illustrative/trust-boundary wording."""
    combined_text = "\n".join(text for _, text in _iter_sample_texts())
    return [
        ValidationProblem(SAMPLE_DIR, f"missing boundary phrase: {phrase}")
        for phrase in BOUNDARY_PHRASES
        if phrase not in combined_text
    ]


def _collect_review_result_limitation_problems() -> list[ValidationProblem]:
    """Require reviewer-result limitation acknowledgements to be true."""
    review_result_path = SAMPLE_DIR / "reviewer-handoff-review-result.json"
    try:
        review_result = _load_json(review_result_path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [ValidationProblem(review_result_path, f"cannot inspect result: {exc}")]

    limitations = review_result.get("limitations_acknowledged")
    if not isinstance(limitations, dict):
        return [
            ValidationProblem(
                review_result_path,
                "limitations_acknowledged must be an object",
            )
        ]

    problems: list[ValidationProblem] = []
    for field in REQUIRED_REVIEW_RESULT_LIMITATIONS:
        if limitations.get(field) is not True:
            problems.append(
                ValidationProblem(
                    review_result_path,
                    f"limitation acknowledgement must be true: {field}",
                )
            )
    return problems


def _artifact_names_from_walkthrough() -> tuple[str, ...]:
    """Extract expected JSON artifact names from the walkthrough artifact map."""
    text = WALKTHROUGH_PATH.read_text(encoding="utf-8")
    return tuple(
        artifact_name
        for artifact_name in EXPECTED_ARTIFACT_CHAIN
        if f"`{artifact_name}`" in text
    )


def _collect_chain_reference_problems() -> list[ValidationProblem]:
    """Validate sample artifact-chain references and schema-id correlations."""
    problems: list[ValidationProblem] = []
    packet_path = SAMPLE_DIR / "reviewer-evidence-packet.json"
    validation_path = SAMPLE_DIR / "key-provenance-validation.json"
    result_validation_path = SAMPLE_DIR / "key-provenance-result-validation.json"
    review_result_validation_path = (
        SAMPLE_DIR / "reviewer-review-result-validation.json"
    )
    review_result_report_validation_path = (
        SAMPLE_DIR / "reviewer-review-result-report-validation.json"
    )
    package_validation_path = (
        SAMPLE_DIR / "reviewer-handoff-package-validation.json"
    )
    quickstart_command_validation_path = (
        SAMPLE_DIR / "reviewer-handoff-quickstart-command-validation.json"
    )
    readme_path = SAMPLE_DIR / "README.md"

    try:
        packet = _load_json(packet_path)
        validation_report = _load_json(validation_path)
        result_validation_report = _load_json(result_validation_path)
        review_result_validation_report = _load_json(review_result_validation_path)
        review_result_report_validation_report = _load_json(
            review_result_report_validation_path
        )
        package_validation_report = _load_json(package_validation_path)
        quickstart_command_validation_report = _load_json(
            quickstart_command_validation_path
        )
        readme_text = readme_path.read_text(encoding="utf-8")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [ValidationProblem(SAMPLE_DIR, f"cannot inspect chain: {exc}")]

    key_provenance = packet.get("key_provenance")
    if key_provenance != EXPECTED_KEY_PROVENANCE_REFERENCES:
        problems.append(
            ValidationProblem(
                packet_path,
                "key_provenance references do not match expected sample artifacts",
            )
        )

    notes_text = "\n".join(str(note) for note in packet.get("reviewer_notes", []))
    for artifact_name in EXPECTED_ARTIFACT_CHAIN:
        if artifact_name not in notes_text and artifact_name not in readme_text:
            problems.append(
                ValidationProblem(
                    packet_path,
                    f"missing chain artifact {artifact_name}",
                )
            )

    readme_positions = []
    for artifact_name in EXPECTED_ARTIFACT_CHAIN:
        try:
            readme_positions.append(readme_text.index(artifact_name))
        except ValueError:
            problems.append(
                ValidationProblem(readme_path, f"missing artifact {artifact_name}")
            )
    if readme_positions != sorted(readme_positions):
        problems.append(
            ValidationProblem(
                readme_path,
                "artifact chain order does not match walkthrough",
            )
        )

    if _artifact_names_from_walkthrough() != EXPECTED_ARTIFACT_CHAIN:
        problems.append(
            ValidationProblem(
                WALKTHROUGH_PATH,
                "walkthrough artifact names do not match the sample chain",
            )
        )

    expected_verification_schema_id = _schema_id(
        SAMPLE_SCHEMA_CASES["verification-result.json"]
    )
    if (
        validation_report.get("verification_result_schema_id")
        != expected_verification_schema_id
    ):
        problems.append(
            ValidationProblem(
                validation_path,
                "verification_result_schema_id does not reference "
                "the verification result schema",
            )
        )

    expected_validation_schema_id = _schema_id(
        SAMPLE_SCHEMA_CASES["key-provenance-validation.json"]
    )
    if (
        result_validation_report.get("validated_schema_id")
        != expected_validation_schema_id
    ):
        problems.append(
            ValidationProblem(
                result_validation_path,
                "validated_schema_id does not reference the validation report schema",
            )
        )

    for key, expected in (
        ("receipt_schema_id", TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID),
        ("report_schema_id", TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID),
    ):
        if validation_report.get(key) != expected:
            problems.append(ValidationProblem(validation_path, f"unexpected {key}"))

    if (
        result_validation_report.get("report_schema_id")
        != TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(result_validation_path, "unexpected report_schema_id")
        )

    if (
        review_result_validation_report.get("validated_schema_id")
        != REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                review_result_validation_path,
                "validated_schema_id does not reference the review result schema",
            )
        )

    if (
        review_result_validation_report.get("report_schema_id")
        != REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                review_result_validation_path,
                "unexpected review-result validation report_schema_id",
            )
        )

    if (
        review_result_validation_report.get("validator")
        != VALIDATE_REVIEW_RESULT_VALIDATOR
    ):
        problems.append(
            ValidationProblem(
                review_result_validation_path,
                "unexpected review-result validator",
            )
        )

    if (
        review_result_report_validation_report.get("validated_schema_id")
        != REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                review_result_report_validation_path,
                "validated_schema_id does not reference the review-result "
                "validation report schema",
            )
        )

    if (
        review_result_report_validation_report.get("report_schema_id")
        != REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                review_result_report_validation_path,
                "unexpected review-result report-validation report_schema_id",
            )
        )

    if (
        review_result_report_validation_report.get("validator")
        != VALIDATE_REVIEW_RESULT_REPORT_VALIDATOR
    ):
        problems.append(
            ValidationProblem(
                review_result_report_validation_path,
                "unexpected review-result report validator",
            )
        )

    if (
        package_validation_report.get("validated_schema_id")
        != TRUSTED_PUBLIC_KEY_PROVENANCE_REVIEW_SAMPLE_MANIFEST_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                package_validation_path,
                "validated_schema_id does not reference the sample manifest schema",
            )
        )

    if (
        package_validation_report.get("report_schema_id")
        != REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                package_validation_path,
                "unexpected package validation report_schema_id",
            )
        )

    if (
        package_validation_report.get("validator")
        != VALIDATE_REVIEWER_HANDOFF_PACKAGE_VALIDATOR
    ):
        problems.append(
            ValidationProblem(
                package_validation_path,
                "unexpected package validator",
            )
        )

    if quickstart_command_validation_report.get("ok") is not True:
        problems.append(
            ValidationProblem(
                quickstart_command_validation_path,
                "quickstart command validation report must be ok",
            )
        )

    if (
        quickstart_command_validation_report.get("report_schema_id")
        != REVIEWER_HANDOFF_QUICKSTART_COMMAND_VALIDATION_REPORT_SCHEMA_ID
    ):
        problems.append(
            ValidationProblem(
                quickstart_command_validation_path,
                "unexpected quickstart command validation report_schema_id",
            )
        )

    if (
        quickstart_command_validation_report.get("validator")
        != QUICKSTART_COMMAND_VALIDATOR
    ):
        problems.append(
            ValidationProblem(
                quickstart_command_validation_path,
                "unexpected quickstart command validator",
            )
        )

    return problems


def validate_key_provenance_review_samples() -> list[ValidationProblem]:
    """Return all Trusted Public Key Provenance sample validation problems."""
    problems: list[ValidationProblem] = []
    problems.extend(_collect_file_and_schema_problems())
    if problems:
        return problems
    problems.extend(_collect_manifest_problems())
    problems.extend(_collect_safety_problems())
    problems.extend(_collect_boundary_problems())
    problems.extend(_collect_review_result_limitation_problems())
    problems.extend(_collect_chain_reference_problems())
    return problems


def main() -> int:
    """Run the Trusted Public Key Provenance sample CI gate."""
    problems = validate_key_provenance_review_samples()
    if not problems:
        print("Trusted Public Key Provenance review samples validated.")
        return 0

    print("[SAMPLES] Trusted Public Key Provenance review samples are invalid:")
    for problem in problems:
        print(f"- {problem.format()}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
