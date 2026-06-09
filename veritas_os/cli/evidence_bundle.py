"""CLI for generating and verifying VERITAS evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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

    if args.json:
        print(json.dumps(verify_result, indent=2, sort_keys=True, ensure_ascii=False))
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
