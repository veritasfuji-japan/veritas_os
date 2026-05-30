#!/usr/bin/env python3
"""Verify the Reviewer Evidence Packet artifact manifest locally/offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.build_reviewer_evidence_artifact_manifest import (  # noqa: E402
    ARTIFACT_NAME,
    BOUNDARY_NOTE,
    DEFAULT_OUTPUT_FILENAME,
    MANIFEST_ID,
    MANIFEST_VERSION,
    REQUIRED_FILE_DEFINITIONS,
    compute_reviewer_evidence_artifact_manifest_hash,
)

VERIFIER_ID = "reviewer-evidence-artifact-manifest-verifier-v1"
VERIFIER_VERSION = "v1"
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVIEWER_NOTES = [
    (
        "This verifier checks a local/offline Reviewer Evidence Artifact Manifest "
        "against files in the artifact directory."
    ),
    (
        "It recomputes manifest_hash, file sha256 hashes, and file byte sizes."
    ),
    (
        "It does not connect to live SaaS, IAM, IdP, SSO, customer directories, "
        "banks, sanctions systems, production approval workflows, or live audit stores."
    ),
    (
        "It is not legal advice, regulatory approval, third-party certification, "
        "production audit certification, or proof of live deployment."
    ),
]
CHECK_NAMES = [
    "manifest_exists",
    "manifest_json_parseable",
    "manifest_id_valid",
    "manifest_version_valid",
    "artifact_name_valid",
    "local_offline_only_valid",
    "manifest_hash_present",
    "manifest_hash_length_valid",
    "manifest_hash_recomputes",
    "required_files_present",
    "file_hashes_match",
    "file_sizes_match",
    "no_unexpected_missing_required_files",
]
EXPECTED_FILE_RESULT_FIELDS = [
    "path",
    "role",
    "required",
    "exists",
    "expected_sha256",
    "actual_sha256",
    "sha256_matches",
    "expected_size_bytes",
    "actual_size_bytes",
    "size_matches",
    "status",
]


def _sha256_bytes(raw: bytes) -> str:
    """Return a lowercase SHA-256 hex digest for raw bytes."""
    return hashlib.sha256(raw).hexdigest()


def _empty_checks() -> dict[str, bool]:
    """Return all verifier checks initialized to ``False``."""
    return {name: False for name in CHECK_NAMES}


def _is_relative_safe_path(value: Any) -> bool:
    """Return whether ``value`` is a relative artifact path."""
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _failure_reasons(checks: dict[str, bool]) -> list[str]:
    """Map failed checks to deterministic failure reason strings."""
    reasons: list[str] = []
    if not checks["manifest_exists"]:
        reasons.append("artifact_manifest_missing")
    if checks["manifest_exists"] and not checks["manifest_json_parseable"]:
        reasons.append("artifact_manifest_json_unparseable")
    if not checks["manifest_id_valid"]:
        reasons.append("artifact_manifest_id_invalid")
    if not checks["manifest_version_valid"]:
        reasons.append("artifact_manifest_version_invalid")
    if not checks["artifact_name_valid"]:
        reasons.append("artifact_manifest_artifact_name_invalid")
    if not checks["local_offline_only_valid"]:
        reasons.append("artifact_manifest_local_offline_only_invalid")
    if not checks["manifest_hash_present"]:
        reasons.append("artifact_manifest_hash_missing")
    if not checks["manifest_hash_length_valid"]:
        reasons.append("artifact_manifest_hash_length_invalid")
    if not checks["manifest_hash_recomputes"]:
        reasons.append("artifact_manifest_hash_mismatch")
    if not checks["required_files_present"]:
        reasons.append("artifact_manifest_required_file_missing")
    if not checks["file_hashes_match"]:
        reasons.append("artifact_manifest_file_hash_mismatch")
    if not checks["file_sizes_match"]:
        reasons.append("artifact_manifest_file_size_mismatch")
    if not checks["no_unexpected_missing_required_files"]:
        reasons.append("artifact_manifest_file_entry_invalid")
    return reasons


def _base_report(
    *,
    artifact_dir: Path,
    manifest_path: Path,
    checks: dict[str, bool],
    file_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic verifier report skeleton."""
    results = [] if file_results is None else file_results
    missing_required_files = [
        result["path"]
        for result in results
        if result.get("required") is True and result.get("exists") is False
    ]
    aggregate_summary = {
        "total_files": len(results),
        "verified_files": sum(
            1 for result in results if result.get("status") == "verified"
        ),
        "missing_files": sum(
            1 for result in results if result.get("status") == "missing"
        ),
        "hash_mismatched_files": sum(
            1 for result in results if result.get("status") == "hash_mismatch"
        ),
        "size_mismatched_files": sum(
            1 for result in results if result.get("status") == "size_mismatch"
        ),
        "required_files": sum(1 for result in results if result.get("required") is True),
        "missing_required_files": missing_required_files,
        "local_offline_only": True,
    }
    reasons = _failure_reasons(checks)
    return {
        "verifier_id": VERIFIER_ID,
        "verifier_version": VERIFIER_VERSION,
        "artifact_name": ARTIFACT_NAME,
        "manifest_path": str(manifest_path),
        "status": "pass" if not reasons else "fail",
        "local_offline_only": True,
        "checks": checks,
        "file_results": results,
        "aggregate_summary": aggregate_summary,
        "failure_reasons": reasons,
        "reviewer_notes": list(REVIEWER_NOTES),
        "boundary_note": BOUNDARY_NOTE,
    }


def _invalid_file_result(entry: Any) -> dict[str, Any]:
    """Return a deterministic file result for an invalid manifest file entry."""
    path = entry.get("path") if isinstance(entry, dict) else None
    role = entry.get("role") if isinstance(entry, dict) else None
    required = entry.get("required") if isinstance(entry, dict) else None
    return {
        "path": path if isinstance(path, str) else None,
        "role": role if isinstance(role, str) else None,
        "required": required if isinstance(required, bool) else None,
        "exists": False,
        "expected_sha256": None,
        "actual_sha256": None,
        "sha256_matches": False,
        "expected_size_bytes": None,
        "actual_size_bytes": None,
        "size_matches": False,
        "status": "invalid_entry",
    }


def _file_result(*, artifact_dir: Path, entry: Any) -> dict[str, Any]:
    """Verify one manifest file entry against local artifact bytes."""
    if not isinstance(entry, dict):
        return _invalid_file_result(entry)

    relative_path = entry.get("path")
    role = entry.get("role")
    required = entry.get("required")
    expected_sha256 = entry.get("sha256")
    expected_size = entry.get("size_bytes")
    if (
        not _is_relative_safe_path(relative_path)
        or not isinstance(role, str)
        or not isinstance(required, bool)
        or not isinstance(expected_sha256, str)
        or not HASH_PATTERN.fullmatch(expected_sha256)
        or not isinstance(expected_size, int)
        or expected_size < 0
    ):
        return _invalid_file_result(entry)

    file_path = artifact_dir / relative_path
    exists = file_path.is_file()
    actual_sha256 = None
    actual_size = None
    sha256_matches = False
    size_matches = False
    status = "missing"
    if exists:
        raw = file_path.read_bytes()
        actual_sha256 = _sha256_bytes(raw)
        actual_size = len(raw)
        sha256_matches = actual_sha256 == expected_sha256
        size_matches = actual_size == expected_size
        if not sha256_matches:
            status = "hash_mismatch"
        elif not size_matches:
            status = "size_mismatch"
        else:
            status = "verified"

    return {
        "path": relative_path,
        "role": role,
        "required": required,
        "exists": exists,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "sha256_matches": sha256_matches,
        "expected_size_bytes": expected_size,
        "actual_size_bytes": actual_size,
        "size_matches": size_matches,
        "status": status,
    }


def verify_reviewer_evidence_artifact_manifest(
    *,
    artifact_dir: Path | str,
    manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    """Verify a Reviewer Evidence Artifact Manifest against local files.

    Args:
        artifact_dir: Local artifact directory to verify. The verifier reads only
            files under this directory and performs no network or credential I/O.
        manifest_path: Optional manifest path. When omitted, the verifier reads
            ``reviewer-evidence-artifact-manifest.json`` inside ``artifact_dir``.

    Returns:
        Deterministic JSON-friendly verification report with pass/fail checks,
        per-file results, aggregate counts, reviewer notes, and boundary notes.
    """
    artifact_path = Path(artifact_dir)
    manifest_file = (
        Path(manifest_path)
        if manifest_path is not None
        else artifact_path / DEFAULT_OUTPUT_FILENAME
    )
    checks = _empty_checks()
    checks["manifest_exists"] = manifest_file.is_file()
    if not checks["manifest_exists"]:
        return _base_report(
            artifact_dir=artifact_path,
            manifest_path=manifest_file,
            checks=checks,
        )

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _base_report(
            artifact_dir=artifact_path,
            manifest_path=manifest_file,
            checks=checks,
        )
    if not isinstance(manifest, dict):
        return _base_report(
            artifact_dir=artifact_path,
            manifest_path=manifest_file,
            checks=checks,
        )

    checks["manifest_json_parseable"] = True
    checks["manifest_id_valid"] = manifest.get("manifest_id") == MANIFEST_ID
    checks["manifest_version_valid"] = (
        manifest.get("manifest_version") == MANIFEST_VERSION
    )
    checks["artifact_name_valid"] = manifest.get("artifact_name") == ARTIFACT_NAME
    checks["local_offline_only_valid"] = manifest.get("local_offline_only") is True

    manifest_hash = manifest.get("manifest_hash")
    checks["manifest_hash_present"] = isinstance(manifest_hash, str) and bool(
        manifest_hash
    )
    checks["manifest_hash_length_valid"] = isinstance(
        manifest_hash, str
    ) and bool(HASH_PATTERN.fullmatch(manifest_hash))
    if checks["manifest_hash_length_valid"]:
        recomputed_hash = compute_reviewer_evidence_artifact_manifest_hash(manifest)
        checks["manifest_hash_recomputes"] = recomputed_hash == manifest_hash

    file_entries = manifest.get("files")
    if not isinstance(file_entries, list):
        file_entries = []
    file_results = [
        _file_result(artifact_dir=artifact_path, entry=entry) for entry in file_entries
    ]
    required_paths = {
        str(definition["path"]) for definition in REQUIRED_FILE_DEFINITIONS
    }
    listed_required_paths = {
        result["path"]
        for result in file_results
        if result["required"] is True and isinstance(result["path"], str)
    }
    missing_required_paths = {
        result["path"]
        for result in file_results
        if result["required"] is True and result["exists"] is False
    }
    invalid_required_paths = {
        result["path"]
        for result in file_results
        if result["required"] is True and result["status"] == "invalid_entry"
    }
    missing_defined_required_paths = required_paths - listed_required_paths

    checks["required_files_present"] = not (
        missing_required_paths or missing_defined_required_paths
    )
    checks["file_hashes_match"] = all(
        result["sha256_matches"]
        for result in file_results
        if result["status"] != "invalid_entry"
    ) and not any(result["status"] == "invalid_entry" for result in file_results)
    checks["file_sizes_match"] = all(
        result["size_matches"]
        for result in file_results
        if result["status"] != "invalid_entry"
    ) and not any(result["status"] == "invalid_entry" for result in file_results)
    checks["no_unexpected_missing_required_files"] = not (
        missing_defined_required_paths or invalid_required_paths
    )

    return _base_report(
        artifact_dir=artifact_path,
        manifest_path=manifest_file,
        checks=checks,
        file_results=file_results,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Verify the Reviewer Evidence Packet artifact manifest."
    )
    parser.add_argument("artifact_dir", help="Reviewer evidence artifact directory")
    parser.add_argument(
        "--manifest-path",
        help="Optional explicit reviewer evidence artifact manifest path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print deterministic verification JSON and return a status exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = verify_reviewer_evidence_artifact_manifest(
        artifact_dir=args.artifact_dir,
        manifest_path=args.manifest_path,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
