"""CLI for generating and verifying VERITAS evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import jsonschema

from veritas_os.audit.evidence_bundle import generate_evidence_bundle
from veritas_os.audit.verify_bundle import verify_evidence_bundle
from veritas_os.security.signing import verify_payload_signature


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
VERIFICATION_RESULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "evidence_bundle_verification_result.schema.json"
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
                    "malformed JSON: "
                    f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
                ),
            }
        ]

    try:
        schema = json.loads(
            VERIFICATION_RESULT_SCHEMA_PATH.read_text(encoding="utf-8")
        )
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
    as UTF-8 audit evidence, including schema validation failure reports.
    """
    errors = _validate_verification_result_schema(result_path)
    output = {
        "ok": not errors,
        "schema_valid": not errors,
        "result_path": str(result_path),
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
                    "error: failed to write validation report "
                    f"to {output_path}: {exc}",
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
    parser = argparse.ArgumentParser(description="Generate/verify VERITAS evidence bundles")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate evidence bundle")
    gen.add_argument("--bundle-type", required=True, choices=["decision", "incident", "release"])
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
