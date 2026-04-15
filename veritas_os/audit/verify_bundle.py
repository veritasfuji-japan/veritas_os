"""Evidence Bundle verification for tamper detection.

Verifies the integrity of a VERITAS evidence bundle by:
1. Checking manifest schema and required fields
2. Recomputing file hashes and comparing to manifest
3. Verifying manifest signature (if present)
4. Validating witness entries within the bundle
"""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from veritas_os.audit.evidence_bundle_schema import (
    BUNDLE_TYPE_CONTENTS,
    BUNDLE_SCHEMA_VERSION,
    BUNDLE_TYPES,
    MANIFEST_REQUIRED_FIELDS,
    validate_decision_snapshot_shape,
)

_logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_evidence_bundle(
    bundle_dir: Path,
    *,
    verify_signature_fn: Optional[Callable[[str, str], bool]] = None,
    verify_witness_signatures: bool = False,
    witness_signature_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Dict[str, Any]:
    """Verify an evidence bundle for integrity and tamper detection.

    Args:
        bundle_dir: Path to the evidence bundle directory.
        verify_signature_fn: Optional callable (payload_hash, signature) -> bool
            for verifying the manifest signature.
        verify_witness_signatures: Whether to verify witness entry signatures.
        witness_signature_fn: Optional callable for witness signature verification.

    Returns:
        Dict with verification result including:
        - ok: bool
        - tampered: bool
        - errors: list of error descriptions
        - manifest: the manifest contents
        - file_hash_results: per-file hash comparison
    """
    result: Dict[str, Any] = {
        "ok": True,
        "tampered": False,
        "errors": [],
        "warnings": [],
        "manifest": None,
        "file_hash_results": {},
    }
    errors: List[str] = result["errors"]
    warnings: List[str] = result["warnings"]

    # Load manifest
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json not found in bundle")
        result["ok"] = False
        result["tampered"] = True
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"Failed to read manifest.json: {exc}")
        result["ok"] = False
        result["tampered"] = True
        return result

    result["manifest"] = manifest

    # Validate schema version
    schema_version = manifest.get("schema_version")
    if schema_version != BUNDLE_SCHEMA_VERSION:
        warnings.append(
            f"Schema version mismatch: expected {BUNDLE_SCHEMA_VERSION}, got {schema_version}"
        )

    # Validate required fields
    missing_fields = MANIFEST_REQUIRED_FIELDS - set(manifest.keys())
    if missing_fields:
        errors.append(f"Missing required manifest fields: {sorted(missing_fields)}")
        result["ok"] = False

    # Validate bundle type
    bundle_type = manifest.get("bundle_type")
    if bundle_type not in BUNDLE_TYPES:
        errors.append(f"Invalid bundle_type: {bundle_type}")
        result["ok"] = False
    else:
        required_contents = BUNDLE_TYPE_CONTENTS.get(bundle_type, {}).get("required", [])
        for required in required_contents:
            if not (bundle_dir / required).exists():
                errors.append(f"Required bundle content missing: {required}")
                result["tampered"] = True

    if bundle_type == "decision":
        decision_record_path = bundle_dir / "decision_record.json"
        if decision_record_path.exists():
            try:
                decision_record = json.loads(decision_record_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"Failed to read decision_record.json: {exc}")
                result["tampered"] = True
            else:
                shape_errors = validate_decision_snapshot_shape(decision_record)
                if shape_errors:
                    errors.extend(shape_errors)
                    result["tampered"] = True
        else:
            errors.append("decision bundle missing decision_record.json")
            result["tampered"] = True

    # Verify file hashes
    expected_hashes = manifest.get("file_hashes", {})
    hash_results: Dict[str, Dict[str, Any]] = {}

    for rel_path, expected_hash in sorted(expected_hashes.items()):
        file_path = bundle_dir / rel_path
        if not file_path.exists():
            hash_results[rel_path] = {
                "ok": False,
                "error": "file_missing",
                "expected": expected_hash,
            }
            errors.append(f"File missing: {rel_path}")
            result["tampered"] = True
            continue

        actual_hash = _sha256_file(file_path)
        if actual_hash != expected_hash:
            hash_results[rel_path] = {
                "ok": False,
                "error": "hash_mismatch",
                "expected": expected_hash,
                "actual": actual_hash,
            }
            errors.append(f"Hash mismatch: {rel_path}")
            result["tampered"] = True
        else:
            hash_results[rel_path] = {"ok": True}

    result["file_hash_results"] = hash_results

    # Check for unexpected files
    expected_files = set(expected_hashes.keys()) | {"manifest.json"}
    for file_path in sorted(bundle_dir.rglob("*")):
        if file_path.is_file():
            rel = str(file_path.relative_to(bundle_dir))
            if rel not in expected_files:
                warnings.append(f"Unexpected file in bundle: {rel}")

    # Verify manifest hash integrity
    stored_manifest_hash = manifest.get("manifest_hash")
    if stored_manifest_hash:
        # Recompute hash from manifest without manifest_hash and signature fields
        manifest_for_hash = {
            k: v for k, v in manifest.items()
            if k not in ("manifest_hash", "manifest_signature", "manifest_signer",
                         "manifest_signature_error")
        }
        from veritas_os.security.hash import sha256_of_canonical_json
        recomputed = sha256_of_canonical_json(manifest_for_hash)
        if recomputed != stored_manifest_hash:
            errors.append("Manifest hash integrity check failed")
            result["tampered"] = True

    # Verify manifest signature
    manifest_signature = manifest.get("manifest_signature")
    if manifest_signature and verify_signature_fn:
        try:
            if not verify_signature_fn(stored_manifest_hash or "", manifest_signature):
                errors.append("Manifest signature verification failed")
                result["tampered"] = True
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Manifest signature verification error: {exc}")

    # Verify witness entries
    witness_path = bundle_dir / "witness_entries.jsonl"
    if witness_path.exists() and verify_witness_signatures and witness_signature_fn:
        try:
            entries: List[Dict[str, Any]] = []
            with witness_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))

            from veritas_os.audit.trustlog_verify import verify_witness_ledger
            witness_result = verify_witness_ledger(
                entries=entries,
                verify_signature_fn=witness_signature_fn,
            )
            result["witness_verification"] = witness_result
            if not witness_result.get("ok"):
                errors.append("Witness ledger verification failed within bundle")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Witness verification skipped: {exc}")

    if errors:
        result["ok"] = False

    return result
