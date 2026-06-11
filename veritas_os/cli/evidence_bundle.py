"""CLI for generating and verifying VERITAS evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import jsonschema

from veritas_os.audit.evidence_bundle import generate_evidence_bundle
from veritas_os.audit.verify_bundle import verify_evidence_bundle


def _parse_key_value_pairs(values: Optional[list[str]]) -> Dict[str, str]:
    """Parse ``key=value`` arguments into a mapping."""
    result: Dict[str, str] = {}
    if not values:
        return result
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid --meta value: {item!r}. expected key=value")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


SECURE_POSTURES = {"secure", "prod"}
SCHEMA_BASE_URL = "https://veritas-os.example/schemas"
VERIFICATION_RESULT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/evidence_bundle_verification_result.schema.json"
)
VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/evidence_bundle_validation_report.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/trusted_public_key_provenance_receipt.schema.json"
)
VALIDATE_RESULT_VALIDATOR = "veritas-evidence-bundle validate-result"
TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/trusted_public_key_provenance_validation_report.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/"
    "trusted_public_key_provenance_result_validation_report.schema.json"
)
VALIDATE_KEY_PROVENANCE_VALIDATOR = "veritas-evidence-bundle validate-key-provenance"
VALIDATE_KEY_PROVENANCE_RESULT_VALIDATOR = (
    "veritas-evidence-bundle validate-key-provenance-result"
)
REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/reviewer_handoff_review_result.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/"
    "reviewer_handoff_review_result_validation_report.schema.json"
)
VALIDATE_REVIEW_RESULT_VALIDATOR = (
    "veritas-evidence-bundle validate-review-result"
)
REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/"
    "reviewer_handoff_review_result_report_validation_report.schema.json"
)
VALIDATE_REVIEW_RESULT_REPORT_VALIDATOR = (
    "veritas-evidence-bundle validate-review-result-report"
)
REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/reviewer_handoff_package_validation_report.schema.json"
)
VALIDATE_REVIEWER_HANDOFF_PACKAGE_VALIDATOR = (
    "veritas-evidence-bundle validate-reviewer-handoff-package"
)
REVIEWER_HANDOFF_PACKAGE_MANIFEST_SCHEMA_ID = (
    f"{SCHEMA_BASE_URL}/"
    "trusted_public_key_provenance_review_sample_manifest.schema.json"
)
VERIFICATION_RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "evidence_bundle_verification_result.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "trusted_public_key_provenance_receipt.schema.json"
)
TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "trusted_public_key_provenance_validation_report.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "reviewer_handoff_review_result.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "reviewer_handoff_review_result_validation_report.schema.json"
)
REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "reviewer_handoff_review_result_report_validation_report.schema.json"
)
REVIEWER_HANDOFF_PACKAGE_MANIFEST_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "trusted_public_key_provenance_review_sample_manifest.schema.json"
)
REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "reviewer_handoff_package_validation_report.schema.json"
)
REVIEWER_EVIDENCE_PACKET_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "en"
    / "demo"
    / "schemas"
    / "reviewer-evidence-packet-v1.schema.json"
)


REVIEW_RESULT_DECISIONS = {"ACCEPT", "REJECT", "NEEDS_FOLLOW_UP"}
REVIEW_RESULT_REQUIRED_LIMITATIONS = {
    "does_not_create_trust",
    "does_not_replace_out_of_band_public_key_trust",
    "not_regulatory_certification",
    "not_completed_third_party_audit_approval",
    "fingerprint_matching_is_correlation_not_standalone_trust",
    "sample_hashes_support_sample_integrity_only",
}
REVIEW_RESULT_REQUIRED_ARTIFACTS = {
    "verification-result.json": VERIFICATION_RESULT_SCHEMA_ID,
    "trusted-public-key-provenance.json": (
        TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID
    ),
    "key-provenance-validation.json": (
        TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID
    ),
    "key-provenance-result-validation.json": (
        TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID
    ),
    "reviewer-evidence-packet.json": (
        "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
    ),
    "sample-artifact-manifest.json": (
        f"{SCHEMA_BASE_URL}/"
        "trusted_public_key_provenance_review_sample_manifest.schema.json"
    ),
}
REVIEW_RESULT_FORBIDDEN_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"-----BEGIN [A-Z ]*(?:PUBLIC|PRIVATE) KEY-----",
        r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]{20,}",
        r"\b[0-9a-f]{64}\b",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bsk_live_[0-9A-Za-z]{12,}\b",
        r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b",
        r"\bghp_[0-9A-Za-z]{20,}\b",
        r"\bgithub_pat_[0-9A-Za-z_]{20,}\b",
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]",
        r"(?:^|\s)/(?:Users|home|tmp|var|workspace)/[^\s,;]*",
        r"[A-Za-z]:\\[^\s,;]*",
        r"Traceback \(most recent call last\)",
        (
            r"\b(?:FileNotFoundError|PermissionError|RuntimeError|"
            r"ValidationError|Exception):"
        ),
        r"jsonschema\.exceptions",
        r"Failed validating",
        r"is a required property",
        r"is not of type",
        r"Additional properties are not allowed",
        r"\bcustomer[_ -]?(?!data\b)[A-Za-z0-9-]{4,}\b",
        r"\bproduction[_ -]?data\b",
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    )
]

REVIEWER_HANDOFF_PACKAGE_REQUIRED_ARTIFACTS = (
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
REVIEWER_HANDOFF_PACKAGE_EXPECTED_ENTRIES = {
    "verification-result.json": {
        "role": "strict_evidence_bundle_verification_result",
        "schema_id": VERIFICATION_RESULT_SCHEMA_ID,
        "schema_path": VERIFICATION_RESULT_SCHEMA_PATH,
    },
    "trusted-public-key-provenance.json": {
        "role": "trusted_public_key_provenance_receipt",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID,
        "schema_path": TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_PATH,
    },
    "key-provenance-validation.json": {
        "role": "key_provenance_validation_report",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID,
        "schema_path": TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_PATH,
    },
    "key-provenance-result-validation.json": {
        "role": "key_provenance_result_validation_report",
        "schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID,
        "schema_path": (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "trusted_public_key_provenance_result_validation_report.schema.json"
        ),
    },
    "reviewer-evidence-packet.json": {
        "role": "reviewer_evidence_packet",
        "schema_id": "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json",
        "schema_path": REVIEWER_EVIDENCE_PACKET_SCHEMA_PATH,
    },
    "reviewer-handoff-review-result.json": {
        "role": "reviewer_handoff_review_result",
        "schema_id": REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID,
        "schema_path": REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_PATH,
    },
    "reviewer-review-result-validation.json": {
        "role": "reviewer_handoff_review_result_validation_report",
        "schema_id": REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID,
        "schema_path": REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_PATH,
    },
    "reviewer-review-result-report-validation.json": {
        "role": "reviewer_handoff_review_result_report_validation_report",
        "schema_id": (
            REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID
        ),
        "schema_path": (
            REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_PATH
        ),
    },
    "reviewer-handoff-package-validation.json": {
        "role": "reviewer_handoff_package_validation_report",
        "schema_id": REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID,
        "schema_path": REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_PATH,
    },
    "README.md": {
        "role": "sample_readme",
        "schema_id": None,
        "schema_path": None,
    },
}
REVIEWER_HANDOFF_PACKAGE_EXPECTED_VALIDATORS = {
    "key-provenance-validation.json": VALIDATE_KEY_PROVENANCE_VALIDATOR,
    "key-provenance-result-validation.json": (
        VALIDATE_KEY_PROVENANCE_RESULT_VALIDATOR
    ),
    "reviewer-review-result-validation.json": VALIDATE_REVIEW_RESULT_VALIDATOR,
    "reviewer-review-result-report-validation.json": (
        VALIDATE_REVIEW_RESULT_REPORT_VALIDATOR
    ),
    "reviewer-handoff-package-validation.json": (
        VALIDATE_REVIEWER_HANDOFF_PACKAGE_VALIDATOR
    ),
}
REVIEWER_HANDOFF_PACKAGE_SYNTHETIC_FINGERPRINT = "1" * 64
REVIEWER_HANDOFF_PACKAGE_FORBIDDEN_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"-----BEGIN [A-Z ]*(?:PUBLIC|PRIVATE) KEY-----",
        r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]{20,}",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        r"\bsk_live_[0-9A-Za-z]{12,}\b",
        r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b",
        r"\bghp_[0-9A-Za-z]{20,}\b",
        r"\bgithub_pat_[0-9A-Za-z_]{20,}\b",
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]",
        r"(?:^|\s)/(?:Users|home|tmp|var|workspace)/[^\s,;]*",
        r"[A-Za-z]:\\[^\s,;]*",
        r"Traceback \(most recent call last\)",
        (
            r"\b(?:FileNotFoundError|PermissionError|RuntimeError|"
            r"ValidationError|Exception):"
        ),
        r"jsonschema\.exceptions",
        r"Failed validating",
        r"is a required property",
        r"is not of type",
        r"Additional properties are not allowed",
        r"\bcustomer[_ -]?(?!data\b)[A-Za-z0-9-]{4,}\b",
        r"\bproduction[_ -]?data\b",
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    )
]


@dataclass(frozen=True)
class KeyProvenanceValidationStatus:
    """Internal validate-key-provenance status without raw input values."""

    receipt_schema_valid: bool
    verification_result_schema_valid: bool
    fingerprint_correlation_ok: bool
    bundle_internal_key_used_ok: bool
    strict_authenticity_ok: bool
    receipt_path_provided: bool
    verification_result_path_provided: bool
    receipt_public_key_fingerprint_present: bool
    verification_result_public_key_fingerprint_present: bool

    @property
    def ok(self) -> bool:
        """Return whether all trusted key provenance checks passed."""
        return (
            self.receipt_schema_valid
            and self.verification_result_schema_valid
            and self.fingerprint_correlation_ok
            and self.bundle_internal_key_used_ok
            and self.strict_authenticity_ok
        )


def _is_fail_closed_posture() -> bool:
    """Return whether evidence-bundle verification must fail closed."""
    return os.getenv("VERITAS_POSTURE", "dev").strip().lower() in SECURE_POSTURES


def _signature_status_label(status: str) -> str:
    """Render a reviewer-facing manifest signature status label."""
    return {
        "pass": "PASS",
        "fail": "FAIL",
        "missing": "FAIL",
        "not_verified": "NOT VERIFIED",
    }.get(status, "NOT VERIFIED")


def _build_signature_verifier(
    public_key_path: Optional[Path],
) -> Optional[Callable[[str, str], bool]]:
    """Build the Ed25519 verifier used for manifest authenticity checks."""
    if public_key_path is None:
        return None

    def _verify(payload_hash: str, signature_b64: str) -> bool:
        from veritas_os.security.signing import verify_payload_signature

        return verify_payload_signature(payload_hash, signature_b64, public_key_path)

    return _verify


def _public_key_fingerprint_sha256(public_key_path: Optional[Path]) -> Optional[str]:
    """Return the SHA-256 hex fingerprint of supplied public key bytes.

    The fingerprint records which public key material was supplied for
    verification. It does not establish trust; reviewers must still obtain and
    validate the public key through an out-of-band trust channel.
    """
    if public_key_path is None:
        return None
    try:
        public_key_bytes = public_key_path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(public_key_bytes).hexdigest()


def _json_schema_error_path(error: jsonschema.ValidationError) -> str:
    """Return a JSONPath-like location for a JSON Schema validation error."""
    path = "$"
    if error.absolute_path:
        path += "".join(f"[{item!r}]" for item in error.absolute_path)
    return path


def _validate_verification_result_schema(
    result_path: Path,
) -> list[dict[str, str]]:
    """Validate a saved Evidence Bundle verification result JSON file.

    The validation is intentionally limited to the saved result document shape.
    It does not re-run Evidence Bundle hash checks or Ed25519 signature
    verification, and it does not establish trusted public key provenance.
    """
    try:
        raw_result = result_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            {
                "path": "$",
                "message": f"failed to read result file {result_path}: {exc}",
            }
        ]

    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError as exc:
        return [
            {
                "path": "$",
                "message": (
                    f"malformed JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}"
                ),
            }
        ]

    try:
        schema = json.loads(VERIFICATION_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            {
                "path": "$",
                "message": f"failed to load verification result schema: {exc}",
            }
        ]

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(result),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    return [
        {"path": _json_schema_error_path(error), "message": error.message}
        for error in errors
    ]


def _load_json_document(document_path: Path) -> tuple[Any, bool]:
    """Load JSON for internal validation without exposing diagnostics."""
    try:
        raw_document = document_path.read_text(encoding="utf-8")
    except OSError:
        return None, False

    try:
        return json.loads(raw_document), True
    except json.JSONDecodeError:
        return None, False


def _load_schema(schema_path: Path) -> tuple[Any, bool]:
    """Load a JSON Schema for internal boolean validation."""
    try:
        return json.loads(schema_path.read_text(encoding="utf-8")), True
    except (OSError, json.JSONDecodeError):
        return None, False


def _json_schema_valid(instance: Any, schema_path: Path) -> bool:
    """Return only whether an instance satisfies a repository JSON Schema."""
    schema, loaded = _load_schema(schema_path)
    if not loaded:
        return False

    validator = jsonschema.Draft202012Validator(schema)
    return not any(validator.iter_errors(instance))


def _strict_authenticity_ok(verification_result: Any) -> bool:
    """Return whether a verification result reports strict authenticity success."""
    if not isinstance(verification_result, dict):
        return False
    return (
        verification_result.get("signature_status") == "pass"
        and verification_result.get("signature_verified") is True
        and verification_result.get("authenticity_ok") is True
    )


def _load_and_check_json_schema(
    document_path: Path,
    schema_path: Path,
) -> tuple[Any, bool]:
    """Load JSON and return only schema validity for public reporting.

    The loaded document may contain externally supplied key material. Callers
    must not expose it directly; this helper returns only the document for
    internal boolean checks and a boolean schema status for public output.
    """
    document, loaded = _load_json_document(document_path)
    if not loaded:
        return document, False
    return document, _json_schema_valid(document, schema_path)


def _build_key_provenance_status(
    receipt_path: Path,
    verification_result_path: Path,
) -> KeyProvenanceValidationStatus:
    """Validate trusted key provenance and return booleans only.

    This function may inspect externally supplied JSON documents internally, but
    it does not return raw JSON values, raw fingerprints, raw file paths, raw
    exception text, or raw JSON Schema validator messages. Public CLI output is
    built separately from this boolean-only status to avoid clear-text logging
    of sensitive or secret-like input values.
    """
    receipt, receipt_schema_valid = _load_and_check_json_schema(
        receipt_path,
        TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_PATH,
    )
    verification_result, verification_result_schema_valid = _load_and_check_json_schema(
        verification_result_path,
        VERIFICATION_RESULT_SCHEMA_PATH,
    )

    receipt_fingerprint = None
    if isinstance(receipt, dict):
        receipt_fingerprint = receipt.get("public_key_fingerprint_sha256")
    verification_fingerprint = None
    if isinstance(verification_result, dict):
        verification_fingerprint = verification_result.get(
            "public_key_fingerprint_sha256"
        )

    receipt_fingerprint_present = isinstance(receipt_fingerprint, str)
    verification_fingerprint_present = isinstance(verification_fingerprint, str)
    fingerprint_correlation_ok = (
        receipt_fingerprint_present
        and verification_fingerprint_present
        and receipt_fingerprint == verification_fingerprint
    )
    bundle_internal_key_used_ok = (
        isinstance(receipt, dict) and receipt.get("bundle_internal_key_used") is False
    )

    return KeyProvenanceValidationStatus(
        receipt_schema_valid=receipt_schema_valid,
        verification_result_schema_valid=verification_result_schema_valid,
        fingerprint_correlation_ok=fingerprint_correlation_ok,
        bundle_internal_key_used_ok=bundle_internal_key_used_ok,
        strict_authenticity_ok=_strict_authenticity_ok(verification_result),
        receipt_path_provided=receipt_path is not None,
        verification_result_path_provided=verification_result_path is not None,
        receipt_public_key_fingerprint_present=receipt_fingerprint_present,
        verification_result_public_key_fingerprint_present=(
            verification_fingerprint_present
        ),
    )


def _key_provenance_public_errors(
    status: KeyProvenanceValidationStatus,
) -> list[dict[str, str]]:
    """Build fixed public diagnostics from boolean validation status."""
    errors: list[dict[str, str]] = []
    if not status.receipt_schema_valid:
        errors.append(
            {
                "check": "receipt_schema_valid",
                "path": "$",
                "message": "receipt does not satisfy schema",
            }
        )
    if not status.verification_result_schema_valid:
        errors.append(
            {
                "check": "verification_result_schema_valid",
                "path": "$",
                "message": "verification result does not satisfy schema",
            }
        )
    if not status.fingerprint_correlation_ok:
        errors.append(
            {
                "check": "fingerprint_correlation_ok",
                "path": "$['public_key_fingerprint_sha256']",
                "message": (
                    "receipt and verification result public key fingerprints "
                    "do not match"
                ),
            }
        )
    if not status.bundle_internal_key_used_ok:
        errors.append(
            {
                "check": "bundle_internal_key_used_ok",
                "path": "$['bundle_internal_key_used']",
                "message": "receipt bundle_internal_key_used must be false",
            }
        )
    if not status.strict_authenticity_ok:
        errors.append(
            {
                "check": "strict_authenticity_ok",
                "path": "$",
                "message": (
                    "verification result must report strict authenticity success"
                ),
            }
        )
    return errors


def _key_provenance_public_report(
    status: KeyProvenanceValidationStatus,
) -> dict[str, Any]:
    """Build public validate-key-provenance JSON from fixed fields only."""
    return {
        "ok": status.ok,
        "receipt_schema_valid": status.receipt_schema_valid,
        "verification_result_schema_valid": (status.verification_result_schema_valid),
        "fingerprint_correlation_ok": status.fingerprint_correlation_ok,
        "bundle_internal_key_used_ok": status.bundle_internal_key_used_ok,
        "strict_authenticity_ok": status.strict_authenticity_ok,
        "receipt_path_provided": status.receipt_path_provided,
        "verification_result_path_provided": (status.verification_result_path_provided),
        "receipt_public_key_fingerprint_present": (
            status.receipt_public_key_fingerprint_present
        ),
        "verification_result_public_key_fingerprint_present": (
            status.verification_result_public_key_fingerprint_present
        ),
        "report_schema_id": (
            TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID
        ),
        "receipt_schema_id": TRUSTED_PUBLIC_KEY_PROVENANCE_RECEIPT_SCHEMA_ID,
        "verification_result_schema_id": VERIFICATION_RESULT_SCHEMA_ID,
        "validator": VALIDATE_KEY_PROVENANCE_VALIDATOR,
        "errors": _key_provenance_public_errors(status),
    }


def _print_key_provenance_human_errors(
    status: KeyProvenanceValidationStatus,
) -> None:
    """Print fixed human diagnostics without interpolating input-derived data."""
    if not status.receipt_schema_valid:
        print("  error [receipt_schema_valid]: receipt does not satisfy schema")
    if not status.verification_result_schema_valid:
        print(
            "  error [verification_result_schema_valid]: "
            "verification result does not satisfy schema"
        )
    if not status.fingerprint_correlation_ok:
        print(
            "  error [fingerprint_correlation_ok]: "
            "receipt and verification result public key fingerprints do not match"
        )
    if not status.bundle_internal_key_used_ok:
        print(
            "  error [bundle_internal_key_used_ok]: "
            "receipt bundle_internal_key_used must be false"
        )
    if not status.strict_authenticity_ok:
        print(
            "  error [strict_authenticity_ok]: "
            "verification result must report strict authenticity success"
        )


def _run_validate_key_provenance(
    receipt_path: Path,
    verification_result_path: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run trusted public key provenance receipt validation."""
    status = _build_key_provenance_status(receipt_path, verification_result_path)
    report = _key_provenance_public_report(status)
    if json_output:
        output_json = json.dumps(report, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError:
                print(
                    "error: failed to write key provenance validation report",
                    file=sys.stderr,
                )
                return 2
        # codeql[py/clear-text-logging-sensitive-data]: validate-key-provenance
        # emits only fixed schema identifiers, booleans, and fixed diagnostics;
        # raw fingerprints, file paths, exception text, schema validator
        # messages, and JSON values are intentionally not emitted.
        print(output_json)
        return 0 if status.ok else 1

    overall_status = "PASS" if status.ok else "FAIL"
    print(f"Trusted public key provenance validation: {overall_status}")
    labels = [
        ("Receipt schema", status.receipt_schema_valid),
        ("Verification result schema", status.verification_result_schema_valid),
        ("Fingerprint correlation", status.fingerprint_correlation_ok),
        ("Bundle-internal key used", status.bundle_internal_key_used_ok),
        ("Strict authenticity result", status.strict_authenticity_ok),
    ]
    for label, passed in labels:
        check_status = "PASS" if passed else "FAIL"
        print(f"{label}: {check_status}")
    _print_key_provenance_human_errors(status)
    return 0 if status.ok else 1


def _key_provenance_result_report_errors(
    *,
    result_readable: bool,
    result_json_valid: bool,
    result_schema_valid: bool,
) -> list[dict[str, str]]:
    """Build fixed diagnostics for saved provenance report validation.

    Diagnostics intentionally do not include raw file paths, exception text,
    schema validator messages, raw fingerprints, or JSON values from the saved
    report because saved validation reports may be externally supplied.
    """
    if not result_readable:
        return [
            {
                "check": "result_readable",
                "path": "$",
                "message": "result file could not be read",
            }
        ]
    if not result_json_valid:
        return [
            {
                "check": "result_json_valid",
                "path": "$",
                "message": "result file is not valid JSON",
            }
        ]
    if not result_schema_valid:
        return [
            {
                "check": "result_schema_valid",
                "path": "$",
                "message": "result does not satisfy schema",
            }
        ]
    return []


def _validate_key_provenance_result_status(
    result_path: Path,
) -> tuple[dict[str, Any], int]:
    """Validate a saved key provenance validation report shape safely.

    The validator checks only the saved ``validate-key-provenance --json``
    report against its JSON Schema. It does not re-run key provenance
    validation, cryptographic verification, trust establishment, regulatory
    certification, or third-party audit approval. Public output is limited to
    booleans, fixed schema identifiers, and fixed diagnostics.
    """
    try:
        raw_report = result_path.read_text(encoding="utf-8")
    except OSError:
        report_document = None
        result_readable = False
        result_json_valid = False
        result_schema_valid = False
        exit_code = 2
    else:
        result_readable = True
        try:
            report_document = json.loads(raw_report)
        except json.JSONDecodeError:
            report_document = None
            result_json_valid = False
            result_schema_valid = False
            exit_code = 1
        else:
            result_json_valid = True
            result_schema_valid = _json_schema_valid(
                report_document,
                TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_PATH,
            )
            exit_code = 0 if result_schema_valid else 1

    output = {
        "ok": result_schema_valid,
        "result_schema_valid": result_schema_valid,
        "validated_schema_id": (
            TRUSTED_PUBLIC_KEY_PROVENANCE_VALIDATION_REPORT_SCHEMA_ID
        ),
        "report_schema_id": (
            TRUSTED_PUBLIC_KEY_PROVENANCE_RESULT_VALIDATION_REPORT_SCHEMA_ID
        ),
        "validator": VALIDATE_KEY_PROVENANCE_RESULT_VALIDATOR,
        "errors": _key_provenance_result_report_errors(
            result_readable=result_readable,
            result_json_valid=result_json_valid,
            result_schema_valid=result_schema_valid,
        ),
    }
    return output, exit_code


def _run_validate_key_provenance_result(
    result_path: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run saved key provenance validation report schema validation."""
    output, exit_code = _validate_key_provenance_result_status(result_path)
    if json_output:
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError:
                print(
                    "error: failed to write key provenance result validation report",
                    file=sys.stderr,
                )
                return 2
        # codeql[py/clear-text-logging-sensitive-data]: this emits only fixed
        # schema identifiers, booleans, and fixed diagnostics; raw paths,
        # fingerprints, exception text, schema validator messages, and saved
        # JSON values are intentionally not emitted.
        print(output_json)
        return exit_code

    status = "PASS" if output["ok"] else "FAIL"
    print(f"Trusted public key provenance validation report schema: {status}")
    for error in output["errors"]:
        print(f"  error [{error['check']}]: {error['message']}")
    return exit_code


def _contains_forbidden_review_result_pattern(value: Any) -> bool:
    """Return whether a review result contains forbidden sensitive text.

    The scan is intentionally boolean-only. Callers must not expose matched text
    because the input may contain keys, fingerprints, local paths, exception
    text, schema validator messages, secrets, or customer/production data.
    """
    if isinstance(value, str):
        return any(
            pattern.search(value) for pattern in REVIEW_RESULT_FORBIDDEN_PATTERNS
        )
    if isinstance(value, dict):
        return any(
            _contains_forbidden_review_result_pattern(item)
            for pair in value.items()
            for item in pair
        )
    if isinstance(value, list):
        return any(
            _contains_forbidden_review_result_pattern(item) for item in value
        )
    return False


def _review_result_decision_valid(result: Any) -> bool:
    """Return whether the reviewer result decision uses the allowed enum."""
    return (
        isinstance(result, dict)
        and result.get("decision") in REVIEW_RESULT_DECISIONS
    )


def _review_result_limitations_acknowledged(result: Any) -> bool:
    """Return whether required limitation acknowledgements are boolean true."""
    if not isinstance(result, dict):
        return False
    limitations = result.get("limitations_acknowledged")
    if not isinstance(limitations, dict):
        return False
    return all(
        isinstance(limitations.get(field), bool) and limitations.get(field) is True
        for field in REVIEW_RESULT_REQUIRED_LIMITATIONS
    )


def _review_result_artifacts_checked_shape_valid(result: Any) -> bool:
    """Return whether all required artifact references are present and checked."""
    if not isinstance(result, dict):
        return False
    artifacts = result.get("artifacts_checked")
    if not isinstance(artifacts, list):
        return False

    observed: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return False
        name = artifact.get("artifact_name")
        schema_id = artifact.get("schema_id")
        checked = artifact.get("checked")
        if not isinstance(name, str) or not isinstance(schema_id, str):
            return False
        if not isinstance(checked, bool) or checked is not True:
            return False
        observed[name] = schema_id

    return all(
        observed.get(name) == schema_id
        for name, schema_id in REVIEW_RESULT_REQUIRED_ARTIFACTS.items()
    )


def _review_result_public_errors(report: dict[str, Any]) -> list[dict[str, str]]:
    """Build fixed diagnostics for review-result validation failures."""
    errors: list[dict[str, str]] = []
    checks = [
        (
            "result_json_valid",
            "result file is not valid JSON or could not be read",
            report["result_json_valid"],
        ),
        (
            "result_schema_valid",
            "review result does not satisfy schema",
            report["result_schema_valid"],
        ),
        (
            "decision_valid",
            "decision must be ACCEPT, REJECT, or NEEDS_FOLLOW_UP",
            report["decision_valid"],
        ),
        (
            "limitations_acknowledged",
            "required limitation acknowledgements must be boolean true",
            report["limitations_acknowledged"],
        ),
        (
            "artifacts_checked_shape_valid",
            "required artifact references must be present and checked",
            report["artifacts_checked_shape_valid"],
        ),
        (
            "forbidden_patterns_absent",
            "review result contains forbidden sensitive or raw diagnostic text",
            report["forbidden_patterns_absent"],
        ),
    ]
    for check, message, passed in checks:
        if not passed:
            errors.append({"check": check, "path": "$", "message": message})
    return errors


def _validate_review_result_status(result_path: Path) -> tuple[dict[str, Any], int]:
    """Validate a saved reviewer handoff review result safely.

    The validator checks JSON parsing, schema conformance, reviewer decision,
    required artifact references, limitation acknowledgement structure, and
    forbidden sensitive/raw diagnostic patterns. Public output is intentionally
    limited to booleans, fixed identifiers, and fixed diagnostics; it does not
    print raw JSON values, raw file paths, raw fingerprints, raw exceptions, raw
    schema validator messages, secrets, or customer/production data.
    """
    result, result_json_valid = _load_json_document(result_path)
    result_schema_valid = (
        result_json_valid
        and _json_schema_valid(result, REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_PATH)
    )
    decision_valid = result_json_valid and _review_result_decision_valid(result)
    limitations_acknowledged = (
        result_json_valid and _review_result_limitations_acknowledged(result)
    )
    artifacts_checked_shape_valid = (
        result_json_valid and _review_result_artifacts_checked_shape_valid(result)
    )
    forbidden_patterns_absent = (
        result_json_valid and not _contains_forbidden_review_result_pattern(result)
    )
    ok = (
        result_schema_valid
        and decision_valid
        and limitations_acknowledged
        and artifacts_checked_shape_valid
        and forbidden_patterns_absent
    )
    report = {
        "ok": ok,
        "result_schema_valid": result_schema_valid,
        "decision_valid": decision_valid,
        "limitations_acknowledged": limitations_acknowledged,
        "artifacts_checked_shape_valid": artifacts_checked_shape_valid,
        "forbidden_patterns_absent": forbidden_patterns_absent,
        "validated_schema_id": REVIEWER_HANDOFF_REVIEW_RESULT_SCHEMA_ID,
        "report_schema_id": (
            REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID
        ),
        "validator": VALIDATE_REVIEW_RESULT_VALIDATOR,
        "errors": [],
    }
    report["errors"] = _review_result_public_errors(
        {**report, "result_json_valid": result_json_valid}
    )
    return report, 0 if ok else 1


def _run_validate_review_result(
    result_path: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run saved reviewer handoff review result validation."""
    output, exit_code = _validate_review_result_status(result_path)
    if json_output:
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError:
                print(
                    "error: failed to write review result validation report",
                    file=sys.stderr,
                )
                return 2
        # codeql[py/clear-text-logging-sensitive-data]: validate-review-result
        # emits only fixed schema identifiers, booleans, and fixed diagnostics.
        print(output_json)
        return exit_code

    status = "PASS" if output["ok"] else "FAIL"
    print(f"Reviewer handoff review result validation: {status}")
    for error in output["errors"]:
        print(f"  error [{error['check']}]: {error['message']}")
    return exit_code


def _review_result_report_errors(
    *,
    result_readable: bool,
    result_json_valid: bool,
    result_schema_valid: bool,
    forbidden_patterns_absent: bool,
) -> list[dict[str, str]]:
    """Build fixed diagnostics for saved review-result report validation.

    Diagnostics intentionally omit raw file paths, raw JSON values, raw
    fingerprints, exception text, schema validator messages, secrets, and
    customer or production data from the externally supplied saved report.
    """
    if not result_readable:
        return [
            {
                "check": "result_readable",
                "path": "$",
                "message": "result file could not be read",
            }
        ]
    if not result_json_valid:
        return [
            {
                "check": "result_json_valid",
                "path": "$",
                "message": "result file is not valid JSON",
            }
        ]

    errors: list[dict[str, str]] = []
    if not result_schema_valid:
        errors.append(
            {
                "check": "result_schema_valid",
                "path": "$",
                "message": "result does not satisfy schema",
            }
        )
    if not forbidden_patterns_absent:
        errors.append(
            {
                "check": "forbidden_patterns_absent",
                "path": "$",
                "message": "result contains forbidden sensitive or raw text",
            }
        )
    return errors


def _validate_review_result_report_status(
    result_path: Path,
) -> tuple[dict[str, Any], int]:
    """Validate a saved validate-review-result JSON report shape safely.

    This second-level validator checks only the saved
    ``validate-review-result --json`` validation report. It validates JSON
    parsing, report schema conformance, fixed validator/schema metadata,
    boolean-only status fields, fixed diagnostics, and absence of sensitive or
    raw diagnostic patterns. It does not re-run reviewer review, create trust,
    replace out-of-band public key trust, prove regulatory certification,
    complete third-party audit approval, or establish cryptographic truth.
    """
    try:
        raw_report = result_path.read_text(encoding="utf-8")
    except OSError:
        report_document = None
        result_readable = False
        result_json_valid = False
        result_schema_valid = False
        forbidden_patterns_absent = False
        exit_code = 2
    else:
        result_readable = True
        try:
            report_document = json.loads(raw_report)
        except json.JSONDecodeError:
            report_document = None
            result_json_valid = False
            result_schema_valid = False
            forbidden_patterns_absent = False
            exit_code = 1
        else:
            result_json_valid = True
            result_schema_valid = _json_schema_valid(
                report_document,
                REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_PATH,
            )
            forbidden_patterns_absent = not _contains_forbidden_review_result_pattern(
                report_document
            )
            exit_code = 0 if result_schema_valid and forbidden_patterns_absent else 1

    ok = result_schema_valid and forbidden_patterns_absent
    output = {
        "ok": ok,
        "result_schema_valid": result_schema_valid,
        "forbidden_patterns_absent": forbidden_patterns_absent,
        "validated_schema_id": (
            REVIEWER_HANDOFF_REVIEW_RESULT_VALIDATION_REPORT_SCHEMA_ID
        ),
        "report_schema_id": (
            REVIEWER_HANDOFF_REVIEW_RESULT_REPORT_VALIDATION_REPORT_SCHEMA_ID
        ),
        "validator": VALIDATE_REVIEW_RESULT_REPORT_VALIDATOR,
        "errors": _review_result_report_errors(
            result_readable=result_readable,
            result_json_valid=result_json_valid,
            result_schema_valid=result_schema_valid,
            forbidden_patterns_absent=forbidden_patterns_absent,
        ),
    }
    return output, exit_code


def _run_validate_review_result_report(
    result_path: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run saved review-result validation report schema validation."""
    output, exit_code = _validate_review_result_report_status(result_path)
    if json_output:
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError:
                print(
                    "error: failed to write review result report validation report",
                    file=sys.stderr,
                )
                return 2
        # codeql[py/clear-text-logging-sensitive-data]: this emits only fixed
        # schema identifiers, booleans, and fixed diagnostics; raw paths,
        # fingerprints, exception text, schema validator messages, secrets,
        # customer data, and saved JSON values are intentionally not emitted.
        print(output_json)
        return exit_code

    status = "PASS" if output["ok"] else "FAIL"
    print(f"Reviewer handoff review result validation report schema: {status}")
    for error in output["errors"]:
        print(f"  error [{error['check']}]: {error['message']}")
    return exit_code


def _safe_child_path(base_dir: Path, artifact_name: str) -> tuple[Path, bool]:
    """Resolve a manifest artifact path without exposing raw path diagnostics."""
    try:
        base_resolved = base_dir.resolve()
        artifact_path = (base_dir / artifact_name).resolve()
        artifact_path.relative_to(base_resolved)
    except (OSError, ValueError):
        return base_dir / artifact_name, False
    return artifact_path, True


def _package_sha256_valid(artifact_path: Path, expected_sha256: Any) -> bool:
    """Return whether an artifact digest matches its manifest digest."""
    if not isinstance(expected_sha256, str):
        return False
    try:
        actual = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual == expected_sha256


def _package_text_is_safe(path: Path) -> bool:
    """Scan an artifact for forbidden sensitive text without returning matches."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            return False
    except OSError:
        return False
    return not any(
        pattern.search(text)
        for pattern in REVIEWER_HANDOFF_PACKAGE_FORBIDDEN_PATTERNS
    )


def _artifact_schema_valid(artifact_path: Path, schema_path: Path | None) -> bool:
    """Validate JSON artifact schema when a schema applies."""
    if schema_path is None:
        return True
    artifact, loaded = _load_json_document(artifact_path)
    return loaded and _json_schema_valid(artifact, schema_path)


def _package_validator_fields_valid(
    artifacts_by_name: dict[str, Path],
) -> bool:
    """Return whether saved validation reports identify expected CLI names."""
    for artifact_name, expected_validator in (
        REVIEWER_HANDOFF_PACKAGE_EXPECTED_VALIDATORS.items()
    ):
        artifact, loaded = _load_json_document(artifacts_by_name[artifact_name])
        if not loaded or not isinstance(artifact, dict):
            return False
        if artifact.get("validator") != expected_validator:
            return False
    return True


def _package_synthetic_fingerprints_valid(
    artifacts_by_name: dict[str, Path],
) -> bool:
    """Require placeholder fingerprints to remain the synthetic sample value."""
    for artifact_name in (
        "verification-result.json",
        "trusted-public-key-provenance.json",
    ):
        artifact, loaded = _load_json_document(artifacts_by_name[artifact_name])
        if not loaded or not isinstance(artifact, dict):
            return False
        if (
            artifact.get("public_key_fingerprint_sha256")
            != REVIEWER_HANDOFF_PACKAGE_SYNTHETIC_FINGERPRINT
        ):
            return False
    return True


def _package_manifest_entries_valid(
    manifest: Any,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Validate manifest names, roles, and schema identifiers."""
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("artifacts"), list
    ):
        return False, {}

    entries_by_name: dict[str, dict[str, Any]] = {}
    for entry in manifest["artifacts"]:
        if not isinstance(entry, dict):
            return False, entries_by_name
        artifact_name = entry.get("artifact_name")
        if not isinstance(artifact_name, str) or artifact_name in entries_by_name:
            return False, entries_by_name
        entries_by_name[artifact_name] = entry

    if tuple(entries_by_name) != REVIEWER_HANDOFF_PACKAGE_REQUIRED_ARTIFACTS:
        return False, entries_by_name

    for artifact_name, expected in (
        REVIEWER_HANDOFF_PACKAGE_EXPECTED_ENTRIES.items()
    ):
        entry = entries_by_name.get(artifact_name)
        if entry is None:
            return False, entries_by_name
        if entry.get("role") != expected["role"]:
            return False, entries_by_name
        if entry.get("schema_id") != expected["schema_id"]:
            return False, entries_by_name
    return True, entries_by_name


def _reviewer_handoff_package_public_errors(
    report: dict[str, Any],
) -> list[dict[str, str]]:
    """Build fixed diagnostics for package validation failures."""
    checks = [
        ("manifest_json_valid", "manifest is not valid JSON or could not be read"),
        ("manifest_schema_valid", "manifest does not satisfy schema"),
        ("artifacts_present", "required artifacts must exist under base dir"),
        ("artifact_hashes_valid", "artifact hashes do not match manifest"),
        ("artifact_schemas_valid", "artifact schemas are not valid"),
        (
            "artifact_relationships_valid",
            "artifact names, roles, schema ids, validators, or placeholders are invalid",
        ),
        (
            "forbidden_patterns_absent",
            "package contains forbidden sensitive or raw diagnostic text",
        ),
    ]
    return [
        {"check": check, "path": "$", "message": message}
        for check, message in checks
        if not report[check]
    ]


def _validate_reviewer_handoff_package_status(
    manifest_path: Path,
    base_dir: Path,
) -> tuple[dict[str, Any], int]:
    """Validate a reviewer handoff sample package from its manifest.

    The package validator checks manifest parsing, manifest schema validity,
    base-directory containment, artifact presence, SHA-256 digests, applicable
    artifact schemas, expected artifact relationships, expected validator CLI
    names, synthetic placeholder fingerprints, and forbidden sensitive or raw
    diagnostic patterns. Public reports are boolean-only and fixed-diagnostic;
    raw artifact contents, raw values, raw fingerprints, raw paths, exception
    text, and raw schema validator messages are intentionally not returned.
    """
    manifest, manifest_json_valid = _load_json_document(manifest_path)
    manifest_schema_valid = (
        manifest_json_valid
        and _json_schema_valid(manifest, REVIEWER_HANDOFF_PACKAGE_MANIFEST_SCHEMA_PATH)
    )
    entries_valid, entries_by_name = _package_manifest_entries_valid(manifest)

    artifacts_present = entries_valid
    artifact_hashes_valid = entries_valid
    artifact_schemas_valid = entries_valid
    forbidden_patterns_absent = _package_text_is_safe(manifest_path)
    artifacts_by_name: dict[str, Path] = {}

    for artifact_name in REVIEWER_HANDOFF_PACKAGE_REQUIRED_ARTIFACTS:
        entry = entries_by_name.get(artifact_name)
        listed_name = artifact_name
        if entry is not None and isinstance(entry.get("artifact_name"), str):
            listed_name = entry["artifact_name"]
        artifact_path, contained = _safe_child_path(base_dir, listed_name)
        if not contained or not artifact_path.is_file():
            artifacts_present = False
            artifact_hashes_valid = False
            artifact_schemas_valid = False
            forbidden_patterns_absent = False
            continue
        artifacts_by_name[artifact_name] = artifact_path
        if entry is None or not _package_sha256_valid(
            artifact_path, entry.get("sha256")
        ):
            artifact_hashes_valid = False
        schema_path = REVIEWER_HANDOFF_PACKAGE_EXPECTED_ENTRIES[artifact_name][
            "schema_path"
        ]
        if not _artifact_schema_valid(artifact_path, schema_path):
            artifact_schemas_valid = False
        if not _package_text_is_safe(artifact_path):
            forbidden_patterns_absent = False

    artifacts_available = all(
        name in artifacts_by_name
        for name in REVIEWER_HANDOFF_PACKAGE_REQUIRED_ARTIFACTS
    )
    validators_valid = artifacts_available and _package_validator_fields_valid(
        artifacts_by_name
    )
    fingerprints_valid = artifacts_available and _package_synthetic_fingerprints_valid(
        artifacts_by_name
    )
    artifact_relationships_valid = (
        entries_valid and validators_valid and fingerprints_valid
    )
    ok = (
        manifest_schema_valid
        and artifacts_present
        and artifact_hashes_valid
        and artifact_schemas_valid
        and artifact_relationships_valid
        and forbidden_patterns_absent
    )
    report = {
        "ok": ok,
        "manifest_schema_valid": manifest_schema_valid,
        "artifacts_present": artifacts_present,
        "artifact_hashes_valid": artifact_hashes_valid,
        "artifact_schemas_valid": artifact_schemas_valid,
        "artifact_relationships_valid": artifact_relationships_valid,
        "forbidden_patterns_absent": forbidden_patterns_absent,
        "validated_schema_id": REVIEWER_HANDOFF_PACKAGE_MANIFEST_SCHEMA_ID,
        "report_schema_id": REVIEWER_HANDOFF_PACKAGE_VALIDATION_REPORT_SCHEMA_ID,
        "validator": VALIDATE_REVIEWER_HANDOFF_PACKAGE_VALIDATOR,
        "errors": [],
    }
    report["errors"] = _reviewer_handoff_package_public_errors(
        {**report, "manifest_json_valid": manifest_json_valid}
    )
    return report, 0 if ok else 1


def _run_validate_reviewer_handoff_package(
    manifest_path: Path,
    base_dir: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run reviewer handoff package validation."""
    output, exit_code = _validate_reviewer_handoff_package_status(
        manifest_path,
        base_dir,
    )
    if json_output:
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError:
                print(
                    "error: failed to write reviewer handoff package validation report",
                    file=sys.stderr,
                )
                return 2
        # codeql[py/clear-text-logging-sensitive-data]: this emits only fixed
        # schema identifiers, booleans, and fixed diagnostics; raw paths,
        # fingerprints, exception text, schema validator messages, secrets,
        # customer data, and saved JSON values are intentionally not emitted.
        print(output_json)
        return exit_code

    status = "PASS" if output["ok"] else "FAIL"
    print(f"Reviewer handoff package validation: {status}")
    for error in output["errors"]:
        print(f"  error [{error['check']}]: {error['message']}")
    return exit_code


def _run_validate_result(
    result_path: Path,
    *,
    json_output: bool = False,
    output_path: Optional[Path] = None,
) -> int:
    """Run saved verification result JSON Schema validation and print status.

    When ``json_output`` is true, stdout is limited to a machine-readable
    validation report for CI, UI, and external audit-tool integrations. When
    ``output_path`` is supplied, the exact stdout JSON report is also written
    as UTF-8 audit evidence, including schema validation failure reports. The
    JSON report includes schema metadata fields for later interpretation; those
    fields do not re-run cryptographic verification or establish trusted key
    provenance.
    """
    errors = _validate_verification_result_schema(result_path)
    output = {
        "ok": not errors,
        "schema_valid": not errors,
        "result_path": str(result_path),
        "report_schema_id": VALIDATION_REPORT_SCHEMA_ID,
        "validated_schema_id": VERIFICATION_RESULT_SCHEMA_ID,
        "validator": VALIDATE_RESULT_VALIDATOR,
        "errors": errors,
    }
    if json_output:
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if output_path is not None:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(output_json + "\n", encoding="utf-8")
            except OSError as exc:
                print(
                    f"error: failed to write validation report to {output_path}: {exc}",
                    file=sys.stderr,
                )
                return 2
        print(output_json)
        return 0 if output["ok"] else 1

    if not errors:
        print("Evidence bundle verification result schema: PASS")
        return 0

    print("Evidence bundle verification result schema: FAIL")
    for error in errors:
        print(f"  error at {error['path']}: {error['message']}")
    return 1


def _dump_json_result(result: Dict[str, Any]) -> str:
    """Serialize a verification result with the stable CLI JSON formatting."""
    return json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)


def _write_verification_result(output_path: Path, result: Dict[str, Any]) -> None:
    """Write the verification result as UTF-8 JSON reviewer evidence.

    Failed verification results are intentionally written too: they are audit
    evidence that a reviewer attempted strict verification and received a
    machine-readable failure result.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_dump_json_result(result) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build argparse parser for evidence bundle CLI."""
    parser = argparse.ArgumentParser(
        description="Generate/verify VERITAS evidence bundles"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate evidence bundle")
    gen.add_argument(
        "--bundle-type", required=True, choices=["decision", "incident", "release"]
    )
    gen.add_argument("--witness-ledger", required=True, type=Path)
    gen.add_argument("--output-dir", required=True, type=Path)
    gen.add_argument("--request-id", action="append", dest="request_ids")
    gen.add_argument("--time-range-start")
    gen.add_argument("--time-range-end")
    gen.add_argument("--created-by", default="veritas_os")
    gen.add_argument(
        "--decision-record-profile",
        choices=["minimum", "full"],
        default="minimum",
    )
    gen.add_argument("--governance-meta", action="append")
    gen.add_argument("--release-meta", action="append")
    gen.add_argument("--incident-meta", action="append")
    gen.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify", help="Verify evidence bundle")
    verify.add_argument("--bundle-dir", required=True, type=Path)
    verify.add_argument(
        "--public-key",
        type=Path,
        help="Trusted Ed25519 public key for manifest signature verification",
    )
    verify.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail when the manifest signature is missing or cannot be verified",
    )
    verify.add_argument("--json", action="store_true")
    verify.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON verification result to this UTF-8 file. "
            "Requires --json and does not suppress stdout JSON."
        ),
    )

    validate = sub.add_parser(
        "validate-result",
        help="Validate a saved verification result JSON file against the schema",
    )
    validate.add_argument(
        "--result",
        required=True,
        type=Path,
        help="Saved JSON result file from verify --json --output",
    )
    validate.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable validation report as JSON",
    )
    validate.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON validation report to this UTF-8 file. "
            "Requires --json and does not suppress stdout JSON."
        ),
    )

    review_result = sub.add_parser(
        "validate-review-result",
        help=(
            "Validate a saved reviewer handoff review result artifact "
            "against its schema and review-boundary checks"
        ),
    )
    review_result.add_argument(
        "--result",
        required=True,
        type=Path,
        help="Saved reviewer-handoff-review-result.json artifact",
    )
    review_result.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable review result validation report as JSON",
    )
    review_result.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON review result validation report to this UTF-8 "
            "file. Requires --json and does not suppress stdout JSON."
        ),
    )

    review_result_report = sub.add_parser(
        "validate-review-result-report",
        help=(
            "Validate a saved validate-review-result JSON validation report "
            "against the schema"
        ),
    )
    review_result_report.add_argument(
        "--result",
        required=True,
        type=Path,
        help="Saved JSON report file from validate-review-result --json",
    )
    review_result_report.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable report validation report as JSON",
    )
    review_result_report.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON review result report validation report to this "
            "UTF-8 file. Requires --json and does not suppress stdout JSON."
        ),
    )

    key_provenance = sub.add_parser(
        "validate-key-provenance",
        help=(
            "Validate trusted public key provenance and correlate it with a "
            "saved strict verification result"
        ),
    )
    key_provenance.add_argument(
        "--receipt",
        required=True,
        type=Path,
        help="Trusted Public Key Provenance Receipt JSON file",
    )
    key_provenance.add_argument(
        "--verification-result",
        required=True,
        type=Path,
        help="Saved JSON result file from verify --json --output",
    )
    key_provenance.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable key provenance validation report as JSON",
    )
    key_provenance.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON key provenance validation report to this UTF-8 "
            "file. Requires --json and does not suppress stdout JSON."
        ),
    )

    key_provenance_result = sub.add_parser(
        "validate-key-provenance-result",
        help=(
            "Validate a saved key provenance validation report JSON file "
            "against the schema"
        ),
    )
    key_provenance_result.add_argument(
        "--result",
        required=True,
        type=Path,
        help="Saved JSON report file from validate-key-provenance --json",
    )
    key_provenance_result.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable result validation report as JSON",
    )
    key_provenance_result.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON key provenance result validation report to this "
            "UTF-8 file. Requires --json and does not suppress stdout JSON."
        ),
    )

    reviewer_package = sub.add_parser(
        "validate-reviewer-handoff-package",
        help=(
            "Validate the reviewer handoff sample package from its manifest, "
            "hashes, schemas, relationships, and safety checks"
        ),
    )
    reviewer_package.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Reviewer handoff sample artifact manifest JSON file",
    )
    reviewer_package.add_argument(
        "--base-dir",
        required=True,
        type=Path,
        help="Directory containing the manifest-listed sample artifacts",
    )
    reviewer_package.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable package validation report as JSON",
    )
    reviewer_package.add_argument(
        "--output",
        type=Path,
        help=(
            "Write the JSON package validation report to this UTF-8 file. "
            "Requires --json and does not suppress stdout JSON."
        ),
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run the evidence bundle CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        try:
            governance = _parse_key_value_pairs(args.governance_meta)
            release = _parse_key_value_pairs(args.release_meta)
            incident = _parse_key_value_pairs(args.incident_meta)
        except ValueError as exc:
            parser.error(str(exc))
            return 2

        result = generate_evidence_bundle(
            bundle_type=args.bundle_type,
            witness_ledger_path=args.witness_ledger,
            output_dir=args.output_dir,
            request_ids=args.request_ids,
            time_range_start=args.time_range_start,
            time_range_end=args.time_range_end,
            governance_identity=governance or None,
            release_provenance=release or None,
            incident_metadata=incident or None,
            decision_record_profile=args.decision_record_profile,
            created_by=args.created_by,
        )
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        else:
            print(f"bundle_dir={result['bundle_dir']}")
            print(f"manifest_hash={result['manifest_hash']}")
            print(f"entry_count={result['entry_count']}")
        return 0

    if args.command == "validate-result":
        if args.output is not None and not args.json:
            parser.error("validate-result --output requires --json")
            return 2
        return _run_validate_result(
            args.result,
            json_output=args.json,
            output_path=args.output,
        )

    if args.command == "validate-review-result":
        if args.output is not None and not args.json:
            parser.error("validate-review-result --output requires --json")
            return 2
        return _run_validate_review_result(
            args.result,
            json_output=args.json,
            output_path=args.output,
        )

    if args.command == "validate-review-result-report":
        if args.output is not None and not args.json:
            parser.error("validate-review-result-report --output requires --json")
            return 2
        return _run_validate_review_result_report(
            args.result,
            json_output=args.json,
            output_path=args.output,
        )

    if args.command == "validate-reviewer-handoff-package":
        if args.output is not None and not args.json:
            parser.error("validate-reviewer-handoff-package --output requires --json")
            return 2
        return _run_validate_reviewer_handoff_package(
            args.manifest,
            args.base_dir,
            json_output=args.json,
            output_path=args.output,
        )

    if args.command == "validate-key-provenance":
        if args.output is not None and not args.json:
            parser.error("validate-key-provenance --output requires --json")
            return 2
        return _run_validate_key_provenance(
            args.receipt,
            args.verification_result,
            json_output=args.json,
            output_path=args.output,
        )

    if args.command == "validate-key-provenance-result":
        if args.output is not None and not args.json:
            parser.error("validate-key-provenance-result --output requires --json")
            return 2
        return _run_validate_key_provenance_result(
            args.result,
            json_output=args.json,
            output_path=args.output,
        )

    if args.output is not None and not args.json:
        parser.error("verify --output requires --json")
        return 2

    require_signature = args.require_signature or _is_fail_closed_posture()
    public_key_fingerprint_sha256 = _public_key_fingerprint_sha256(args.public_key)
    verify_signature_fn = _build_signature_verifier(args.public_key)
    verify_result: Dict[str, Any] = verify_evidence_bundle(
        args.bundle_dir,
        verify_signature_fn=verify_signature_fn,
        require_signature=require_signature,
    )
    verify_result["public_key_fingerprint_sha256"] = public_key_fingerprint_sha256
    if args.public_key is None:
        key_warning = (
            "No trusted public key supplied; manifest signature authenticity "
            "cannot be verified"
        )
        if require_signature:
            if key_warning not in verify_result["errors"]:
                verify_result["errors"].append(key_warning)
            verify_result["ok"] = False
        elif key_warning not in verify_result["warnings"]:
            verify_result["warnings"].append(key_warning)

    if args.output is not None:
        try:
            _write_verification_result(args.output, verify_result)
        except OSError as exc:
            print(
                f"error: failed to write verification result to {args.output}: {exc}",
                file=sys.stderr,
            )
            return 2

    if args.json:
        print(_dump_json_result(verify_result))
    else:
        status = "PASS" if verify_result.get("ok") else "FAIL"
        hash_status = "PASS" if verify_result.get("hash_integrity_ok") else "FAIL"
        signature_status = _signature_status_label(
            str(verify_result.get("signature_status", "not_verified"))
        )
        print(f"Evidence bundle verification: {status}")
        print(f"File/hash integrity: {hash_status}")
        print(f"Manifest signature: {signature_status}")
        for err in verify_result.get("errors", []):
            print(f"  error: {err}")
        for warning in verify_result.get("warnings", []):
            print(f"  warning: {warning}")
    return 0 if verify_result.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
