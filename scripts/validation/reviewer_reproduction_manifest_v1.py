#!/usr/bin/env python3
"""Check a third-party-runnable controlled proof bundle without effect authority.

Only byte consistency under a caller-supplied commit SHA is checked. An
independently trusted Git commit / manifest digest is essential for origin trust.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

EXPECTED_FILES = (
    "report.json",
    "evidence.json",
    "reviewer-proof-validation.json",
)
FORMAT = "veritas-controlled-reproduction-bundle/v1"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class BundleError(ValueError):
    """Invalid, incomplete or unsupported reviewer evidence."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise BundleError(code)


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise BundleError("NON_FINITE_JSON")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_bytes(), object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleError("INVALID_JSON") from exc
    require(type(value) is dict, "JSON_OBJECT_REQUIRED")
    return value


def _source_file(root: Path, filename: str) -> Path:
    require(filename in EXPECTED_FILES, "UNEXPECTED_FILE")
    require(not root.is_symlink() and root.is_dir(), "BUNDLE_DIRECTORY_INVALID")
    path = root / filename
    require(not path.is_symlink() and path.is_file(), "MISSING_OR_SYMLINKED_FILE")
    return path


def _sha(value: Any, *, length: int, code: str) -> str:
    require(type(value) is str, code)
    pattern = SHA_PATTERN if length == 40 else DIGEST_PATTERN
    require(pattern.fullmatch(value) is not None, code)
    return value


def _check_proof_payloads(root: Path, expected_sha: str) -> None:
    report = read_json(_source_file(root, "report.json"))
    evidence = read_json(_source_file(root, "evidence.json"))
    validation = read_json(_source_file(root, "reviewer-proof-validation.json"))
    for item in (report, evidence, validation):
        for field in ("tested_sha", "source_sha", "base_sha"):
            require(item.get(field) == expected_sha, "PROOF_CHECKOUT_MISMATCH")
    require(report.get("result") == "PASS", "PROOF_NOT_PASS")
    require(report.get("proof") == "CONTROLLED_CURRENT_HEAD_DECISION_TO_EFFECT_E2E",
            "WRONG_PROOF")
    require(validation.get("result") == "PASS_BOUNDED_CONSISTENCY_ONLY",
            "REVIEWER_CHECK_NOT_PASS")
    require(validation.get("production_proven") is False
            and validation.get("third_party_certified") is False
            and validation.get("independent_effect_observed") is False
            and validation.get("independent_custody_proven") is False
            and validation.get("all_producer_predicates_independently_recomputed") is False,
            "UNSUPPORTED_REVIEWER_CLAIM")
    for field in (
        "production_claim", "production_decision_to_effect_e2e_proven",
        "production_validation_proven", "trustlog_exactly_once_proven",
    ):
        require(report.get(field) is False, "UNSUPPORTED_PRODUCTION_CLAIM")


def make_manifest(
    root: Path,
    expected_sha: str,
    *,
    postgres_version: str,
    python_version: str,
) -> dict[str, Any]:
    """Create a local actor's consistency manifest; never attest identity."""
    _sha(expected_sha, length=40, code="BAD_CHECKOUT_SHA")
    _check_proof_payloads(root, expected_sha)
    files: list[dict[str, Any]] = []
    for name in EXPECTED_FILES:
        contents = _source_file(root, name).read_bytes()
        files.append({
            "path": name, "size_bytes": len(contents), "sha256": sha256(contents),
        })
    record: dict[str, Any] = {
        "format_version": FORMAT,
        "proof_scope": "CONTROLLED_SYNTHETIC_TLS_POSTGRESQL_ONLY",
        "run_mode": "REVIEWER_CONTROLLED_LOCAL_DOCKER",
        "tested_sha": expected_sha,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "python_version": python_version,
        "postgres_version": postgres_version,
        "files": files,
        "producer_reported_evidence_consistency": True,
        "external_effect_or_provider": False,
        "independent_administrative_custody_proven": False,
        "third_party_certified": False,
        "production_proven": False,
        "authentic_origin_proven_by_manifest_alone": False,
    }
    record["manifest_sha256"] = sha256(canonical_bytes(record))
    return record


def verify_bundle(
    root: Path, expected_sha: str, *,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Offline byte verifier. Never reads a key or mutates an external system."""
    _sha(expected_sha, length=40, code="BAD_CHECKOUT_SHA")
    require(not root.is_symlink() and root.is_dir(), "BUNDLE_DIRECTORY_INVALID")
    manifest_path = root / "reproduction-manifest.json"
    require(not manifest_path.is_symlink() and manifest_path.is_file(),
            "MISSING_REPRODUCTION_MANIFEST")
    manifest = read_json(manifest_path)
    require(manifest.get("format_version") == FORMAT, "BAD_MANIFEST_VERSION")
    require(manifest.get("tested_sha") == expected_sha,
            "MANIFEST_CHECKOUT_MISMATCH")
    require(manifest.get("run_mode") == "REVIEWER_CONTROLLED_LOCAL_DOCKER",
            "UNEXPECTED_RUN_MODE")
    for flag in (
        "external_effect_or_provider", "independent_administrative_custody_proven",
        "third_party_certified", "production_proven",
        "authentic_origin_proven_by_manifest_alone",
    ):
        require(manifest.get(flag) is False, "UNSUPPORTED_MANIFEST_CLAIM")
    digest = _sha(manifest.get("manifest_sha256"), length=64,
                  code="BAD_MANIFEST_DIGEST")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    require(sha256(canonical_bytes(unsigned)) == digest,
            "MANIFEST_HASH_MISMATCH")
    if expected_manifest_sha256 is not None:
        _sha(expected_manifest_sha256, length=64,
             code="BAD_EXTERNAL_MANIFEST_PIN")
        require(digest == expected_manifest_sha256, "EXTERNAL_MANIFEST_PIN_MISMATCH")

    entries = manifest.get("files")
    require(type(entries) is list and len(entries) == len(EXPECTED_FILES),
            "WRONG_FILE_SET")
    seen = set()
    for entry in entries:
        require(type(entry) is dict, "INVALID_FILE_ENTRY")
        name = entry.get("path")
        require(type(name) is str and name in EXPECTED_FILES and name not in seen,
                "DUPLICATE_OR_UNEXPECTED_FILE")
        seen.add(name)
        data = _source_file(root, name).read_bytes()
        require(type(entry.get("size_bytes")) is int
                and entry["size_bytes"] == len(data), "FILE_SIZE_MISMATCH")
        _sha(entry.get("sha256"), length=64, code="BAD_FILE_DIGEST")
        require(entry["sha256"] == sha256(data), "FILE_HASH_MISMATCH")
    require(seen == set(EXPECTED_FILES), "MISSING_MANIFEST_FILE")
    _check_proof_payloads(root, expected_sha)
    return {
        "format_version": "veritas-controlled-reproduction-verification/v1",
        "result": "PASS_BUNDLE_CONSISTENCY_ONLY",
        "tested_sha": expected_sha,
        "manifest_sha256": digest,
        "verified_file_count": len(EXPECTED_FILES),
        "origin_authenticity_proven": False,
        "administrative_independence_proven": False,
        "production_proven": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify"])
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--expected-checkout-sha", required=True)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(
            args.bundle, args.expected_checkout_sha,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    except (BundleError, OSError, TypeError, ValueError) as exc:
        print("REVIEWER_REPRODUCTION_FAIL: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
