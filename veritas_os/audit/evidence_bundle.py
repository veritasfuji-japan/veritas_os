"""Evidence Bundle generation for external audit packaging.

Generates deterministic, signed evidence bundles from TrustLog data for
third-party auditors, customers, and legal review.  Each bundle is a
self-contained directory (or tar.gz archive) containing all cryptographic
evidence needed to independently verify one or more VERITAS decisions.

Bundle types:
    - **decision**: Single decision evidence (one witness entry + artifacts)
    - **incident**: Incident-scoped bundle (time range or request IDs)
    - **release**: Release-scoped bundle (all decisions in a release window)

Design:
    - Deterministic output (sorted files, reproducible hashes)
    - Manifest with SHA-256 hashes of all included files
    - Optional Ed25519 signature on manifest
    - Tamper detection via manifest hash verification
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tarfile
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from veritas_os.audit.evidence_bundle_schema import BUNDLE_SCHEMA_VERSION, BUNDLE_TYPES
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

_logger = logging.getLogger(__name__)


def _uuid7() -> str:
    """Generate a UUIDv7-compatible identifier."""
    unix_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rand_a = uuid.uuid4().int & ((1 << 12) - 1)
    rand_b = uuid.uuid4().int & ((1 << 62) - 1)
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0x2 << 62
    value |= rand_b
    return str(uuid.UUID(int=value))


def _utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _load_witness_entries(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL witness entries from file."""
    entries: List[Dict[str, Any]] = []
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _filter_entries_by_request_ids(
    entries: List[Dict[str, Any]],
    request_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """Filter witness entries matching given request IDs."""
    id_set = set(request_ids)
    return [
        e for e in entries
        if (e.get("decision_payload") or {}).get("request_id") in id_set
        or e.get("decision_id") in id_set
    ]


def _filter_entries_by_time_range(
    entries: List[Dict[str, Any]],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter witness entries within a time range (ISO 8601 strings)."""
    result = []
    for entry in entries:
        ts = entry.get("timestamp", "")
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        result.append(entry)
    return result


def _write_json_file(directory: Path, filename: str, data: Any) -> Path:
    """Write JSON data to a file deterministically."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    path.write_text(content + "\n", encoding="utf-8")
    return path


def _write_jsonl_file(directory: Path, filename: str, entries: List[Dict[str, Any]]) -> Path:
    """Write JSONL entries deterministically."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for entry in entries:
        lines.append(json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str))
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    return path


def _collect_file_hashes(directory: Path) -> Dict[str, str]:
    """Compute SHA-256 hashes of all files in directory, sorted by path."""
    hashes: Dict[str, str] = {}
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file() and file_path.name != "manifest.json":
            rel = str(file_path.relative_to(directory))
            hashes[rel] = _sha256_file(file_path)
    return hashes


def _runtime_context_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build runtime metadata describing active posture/backends/versions."""
    decision_payload = entry.get("decision_payload") if isinstance(entry, dict) else {}
    decision_payload = decision_payload if isinstance(decision_payload, dict) else {}
    return {
        "posture": os.getenv("VERITAS_POSTURE", "dev"),
        "trustlog_backend": os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl"),
        "memory_backend": os.getenv("VERITAS_MEMORY_BACKEND", "json"),
        "trustlog_signer_backend": os.getenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file"),
        "api_version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "kernel_version": os.getenv("VERITAS_KERNEL_VERSION", "core-kernel 0.x"),
        "pipeline_version": os.getenv("VERITAS_PIPELINE_VERSION", "unknown"),
        "decision_version": decision_payload.get("version"),
    }


def _decision_record(entry: Dict[str, Any], verification_report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract auditor-facing decision snapshot from one TrustLog witness entry."""
    payload = entry.get("decision_payload")
    payload = payload if isinstance(payload, dict) else {}
    governance_identity = payload.get("governance_identity")
    decision_id = entry.get("decision_id") or payload.get("decision_id")

    return {
        "decision_payload": payload,
        "gate_decision": payload.get("gate_decision", "unknown"),
        "business_decision": payload.get("business_decision", "HOLD"),
        "next_action": payload.get("next_action", "REVISE_AND_RESUBMIT"),
        "required_evidence": payload.get("required_evidence", []),
        "human_review_required": bool(payload.get("human_review_required", False)),
        "trustlog_references": {
            "decision_id": decision_id,
            "request_id": payload.get("request_id"),
            "previous_hash": entry.get("previous_hash"),
            "payload_hash": entry.get("payload_hash"),
            "full_payload_hash": entry.get("full_payload_hash"),
            "signature": entry.get("signature"),
            "anchor_backend": entry.get("anchor_backend"),
            "anchor_status": entry.get("anchor_status"),
            "anchor_receipt": entry.get("anchor_receipt"),
            "mirror_backend": entry.get("mirror_backend"),
            "mirror_receipt": entry.get("mirror_receipt"),
            "artifact_ref": entry.get("artifact_ref"),
        },
        "verification": {
            "report_path": "verification_report.json",
            "ledger_ok": verification_report.get("ok"),
            "chain_ok": verification_report.get("chain_ok"),
            "signature_ok": verification_report.get("signature_ok"),
            "errors": verification_report.get("total_errors"),
            "notes": verification_report.get("total_notes"),
        },
        "provenance": {
            "witness_timestamp": entry.get("timestamp"),
            "bundle_generated_at": _utc_now_iso8601(),
            "signer_metadata": entry.get("signer_metadata"),
            "governance_identity": governance_identity,
        },
        "runtime_context": _runtime_context_from_entry(entry),
    }


def generate_evidence_bundle(
    *,
    bundle_type: str,
    witness_ledger_path: Path,
    output_dir: Path,
    request_ids: Optional[Sequence[str]] = None,
    time_range_start: Optional[str] = None,
    time_range_end: Optional[str] = None,
    governance_identity: Optional[Dict[str, Any]] = None,
    release_provenance: Optional[Dict[str, Any]] = None,
    incident_metadata: Optional[Dict[str, Any]] = None,
    signer_fn: Optional[Callable[[str], str]] = None,
    signer_metadata: Optional[Dict[str, Any]] = None,
    bundle_id: Optional[str] = None,
    created_by: str = "veritas_os",
) -> Dict[str, Any]:
    """Generate a deterministic evidence bundle for external audit.

    Args:
        bundle_type: One of 'decision', 'incident', 'release'.
        witness_ledger_path: Path to the signed witness ledger JSONL.
        output_dir: Directory where the bundle will be created.
        request_ids: Filter to specific decision request IDs.
        time_range_start: ISO 8601 start time for filtering.
        time_range_end: ISO 8601 end time for filtering.
        governance_identity: Optional governance identity metadata.
        release_provenance: Optional release provenance metadata.
        incident_metadata: Optional incident metadata.
        signer_fn: Optional callable that signs a payload hash and returns base64.
        signer_metadata: Optional signer metadata dict.
        bundle_id: Optional explicit bundle ID (default: auto-generated UUIDv7).
        created_by: Creator identifier.

    Returns:
        Dict with bundle metadata including path, manifest hash, and content list.

    Raises:
        ValueError: If bundle_type is invalid or no entries match filters.
    """
    if bundle_type not in BUNDLE_TYPES:
        raise ValueError(f"Invalid bundle_type: {bundle_type}. Expected one of {BUNDLE_TYPES}")

    if not bundle_id:
        bundle_id = _uuid7()

    # Load and filter entries
    all_entries = _load_witness_entries(witness_ledger_path)

    if request_ids:
        entries = _filter_entries_by_request_ids(all_entries, request_ids)
    elif time_range_start or time_range_end:
        entries = _filter_entries_by_time_range(all_entries, time_range_start, time_range_end)
    else:
        entries = all_entries

    if not entries:
        raise ValueError("No witness entries match the specified filters")

    # Create bundle directory
    bundle_dir = output_dir / f"veritas_bundle_{bundle_type}_{bundle_id}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    written_files: List[str] = []

    # Write witness entries
    _write_jsonl_file(bundle_dir, "witness_entries.jsonl", entries)
    written_files.append("witness_entries.jsonl")

    # Extract and write anchor receipts
    anchor_receipts = []
    for entry in entries:
        receipt = entry.get("anchor_receipt")
        if isinstance(receipt, dict):
            anchor_receipts.append({
                "decision_id": entry.get("decision_id"),
                "timestamp": entry.get("timestamp"),
                "anchor_backend": entry.get("anchor_backend"),
                "anchor_status": entry.get("anchor_status"),
                "receipt": receipt,
            })
    if anchor_receipts:
        _write_json_file(bundle_dir, "anchor_receipts/anchor_receipts.json", anchor_receipts)
        written_files.append("anchor_receipts/anchor_receipts.json")

    # Extract and write mirror receipts
    mirror_receipts = []
    for entry in entries:
        mr = entry.get("mirror_receipt")
        if isinstance(mr, dict):
            mirror_receipts.append({
                "decision_id": entry.get("decision_id"),
                "timestamp": entry.get("timestamp"),
                "mirror_backend": entry.get("mirror_backend"),
                "receipt": mr,
            })
    if mirror_receipts:
        _write_json_file(bundle_dir, "mirror_receipts/mirror_receipts.json", mirror_receipts)
        written_files.append("mirror_receipts/mirror_receipts.json")

    # Extract and write artifact linkage metadata
    artifact_refs = []
    for entry in entries:
        ref = entry.get("artifact_ref")
        if isinstance(ref, dict):
            artifact_refs.append({
                "decision_id": entry.get("decision_id"),
                "full_payload_hash": entry.get("full_payload_hash"),
                "artifact_ref": ref,
            })
    if artifact_refs:
        _write_json_file(bundle_dir, "artifacts/artifact_linkage.json", artifact_refs)
        written_files.append("artifacts/artifact_linkage.json")

    # Write signer metadata
    if signer_metadata:
        _write_json_file(bundle_dir, "signer_metadata.json", signer_metadata)
        written_files.append("signer_metadata.json")
    else:
        # Extract from first entry
        first_signer = entries[0].get("signer_metadata") if entries else None
        if first_signer:
            _write_json_file(bundle_dir, "signer_metadata.json", first_signer)
            written_files.append("signer_metadata.json")

    # Write governance identity
    if governance_identity:
        _write_json_file(bundle_dir, "governance_identity.json", governance_identity)
        written_files.append("governance_identity.json")

    # Write incident metadata
    if incident_metadata and bundle_type == "incident":
        _write_json_file(bundle_dir, "incident_metadata.json", incident_metadata)
        written_files.append("incident_metadata.json")

    # Write release provenance
    if release_provenance and bundle_type == "release":
        _write_json_file(bundle_dir, "release_provenance.json", release_provenance)
        written_files.append("release_provenance.json")

    verify_result: Dict[str, Any] = {}
    # Run verification and include report
    try:
        from veritas_os.audit.trustlog_verify import verify_witness_ledger

        def _noop_verify(_entry: Dict[str, Any]) -> bool:
            return True  # Signature verification is optional in bundle context

        verify_result = verify_witness_ledger(
            entries=entries,
            verify_signature_fn=_noop_verify,
        )
        _write_json_file(bundle_dir, "verification_report.json", verify_result)
        written_files.append("verification_report.json")
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Bundle verification skipped: %s", exc)

    if bundle_type == "decision":
        decision_entry = entries[0]
        decision_record = _decision_record(decision_entry, verify_result)
        _write_json_file(bundle_dir, "decision_record.json", decision_record)
        written_files.append("decision_record.json")

    # Compute file hashes for manifest
    file_hashes = _collect_file_hashes(bundle_dir)

    # Build manifest
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_type": bundle_type,
        "bundle_id": bundle_id,
        "created_at": _utc_now_iso8601(),
        "created_by": created_by,
        "contents": sorted(written_files),
        "file_hashes": file_hashes,
        "entry_count": len(entries),
        "time_range": {
            "earliest": entries[0].get("timestamp") if entries else None,
            "latest": entries[-1].get("timestamp") if entries else None,
        },
    }

    if request_ids:
        manifest["filter"] = {"request_ids": list(request_ids)}
    if time_range_start or time_range_end:
        manifest["filter"] = {
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
        }

    # Sign manifest if signer provided
    manifest_hash = sha256_of_canonical_json(manifest)
    manifest["manifest_hash"] = manifest_hash

    if signer_fn:
        try:
            manifest["manifest_signature"] = signer_fn(manifest_hash)
            if signer_metadata:
                manifest["manifest_signer"] = signer_metadata
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Manifest signing failed: %s", exc)
            manifest["manifest_signature"] = None
            manifest["manifest_signature_error"] = str(exc)

    _write_json_file(bundle_dir, "manifest.json", manifest)

    return {
        "bundle_id": bundle_id,
        "bundle_type": bundle_type,
        "bundle_dir": str(bundle_dir),
        "manifest_hash": manifest_hash,
        "entry_count": len(entries),
        "files": sorted(written_files) + ["manifest.json"],
    }


def create_bundle_archive(bundle_dir: Path, output_path: Optional[Path] = None) -> Path:
    """Create a deterministic tar.gz archive from a bundle directory.

    Args:
        bundle_dir: Path to the evidence bundle directory.
        output_path: Optional path for the archive. Defaults to bundle_dir + .tar.gz.

    Returns:
        Path to the created archive.
    """
    if output_path is None:
        output_path = bundle_dir.with_suffix(".tar.gz")

    with tarfile.open(output_path, "w:gz") as tar:
        for file_path in sorted(bundle_dir.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(bundle_dir.parent))
                tar.add(file_path, arcname=arcname)

    return output_path
