"""Unified TrustLog verification utilities.

This module centralizes verification logic for both ledgers:
- encrypted full ledger (``trust_log.jsonl``)
- signed witness ledger (``trustlog.jsonl``)

The public API is intentionally stable:
    - :func:`verify_full_ledger`
    - :func:`verify_witness_ledger`
    - :func:`verify_trustlogs`
"""

from __future__ import annotations

import json
import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from veritas_os.logging.encryption import DecryptionError, EncryptionKeyMissing, decrypt
from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json
from veritas_os.audit.artifact_linkage import verify_entry_artifact_linkage

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


@dataclass
class VerificationError:
    """Structured verification error for CLI/API reporting."""

    ledger: str
    index: int
    reason: str


def _as_dict(error: VerificationError) -> Dict[str, Any]:
    return {"ledger": error.ledger, "index": error.index, "reason": error.reason}


def _canonical_entry_json(entry: Dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _iter_full_entries(log_path: Path) -> Iterable[Dict[str, Any]]:
    if not log_path.exists():
        return
    with log_path.open("r", encoding="utf-8") as file:
        for idx, raw in enumerate(file):
            line = raw.strip()
            if not line:
                continue
            try:
                decoded = decrypt(line)
                entry = json.loads(decoded)
            except (json.JSONDecodeError, ValueError, EncryptionKeyMissing, DecryptionError):
                yield {"__invalid__": True, "__index__": idx, "__reason__": "json_decode_error"}
                continue
            if not isinstance(entry, dict):
                yield {"__invalid__": True, "__index__": idx, "__reason__": "entry_not_dict"}
                continue
            yield entry


def _compute_full_entry_hash(entry: Dict[str, Any], expected_prev: Optional[str]) -> str:
    entry_json = _canonical_entry_json(entry)
    combined = f"{expected_prev}{entry_json}" if expected_prev else entry_json
    return sha256_hex(combined)


def verify_full_ledger(
    log_path: Path,
    max_entries: Optional[int] = None,
) -> Dict[str, Any]:
    """Verify encrypted full-ledger chain integrity."""
    prev_hash: Optional[str] = None
    total_entries = 0
    valid_entries = 0
    errors: List[VerificationError] = []

    for index, entry in enumerate(_iter_full_entries(log_path)):
        if max_entries is not None and total_entries >= max_entries:
            break
        total_entries += 1

        if entry.get("__invalid__"):
            errors.append(VerificationError("full", index, str(entry.get("__reason__", "invalid_entry"))))
            continue

        actual_prev = entry.get("sha256_prev")
        if prev_hash is not None and actual_prev != prev_hash:
            errors.append(VerificationError("full", index, "sha256_prev_mismatch"))
            prev_hash = entry.get("sha256")
            continue

        expected_prev = prev_hash if prev_hash is not None else actual_prev
        expected_hash = _compute_full_entry_hash(entry, expected_prev)
        if entry.get("sha256") != expected_hash:
            errors.append(VerificationError("full", index, "sha256_mismatch"))
            prev_hash = entry.get("sha256")
            continue

        valid_entries += 1
        prev_hash = entry.get("sha256")

    return {
        "ledger": "full",
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "invalid_entries": total_entries - valid_entries,
        "chain_ok": all(err.reason not in {"sha256_prev_mismatch", "sha256_mismatch"} for err in errors),
        "signature_ok": True,
        "linkage_ok": True,
        "mirror_ok": True,
        "last_hash": prev_hash,
        "detailed_errors": [_as_dict(err) for err in errors],
        "ok": len(errors) == 0,
    }


def _entry_chain_hash(entry: Dict[str, Any]) -> str:
    return sha256_hex(canonical_json_dumps(entry))


def _env_flag(name: str, default: bool = False) -> bool:
    """Return ``True`` when the env var is set to a truthy value."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_etag(value: Any) -> str:
    return str(value or "").strip().strip('"')


def _is_s3_receipt(receipt: Dict[str, Any]) -> bool:
    return isinstance(receipt.get("bucket"), str) and isinstance(receipt.get("key"), str)


def _verify_mirror_receipt(
    entry: Dict[str, Any],
    *,
    remote_enabled: bool,
    strict_mode: bool,
    strict_s3: bool,
    require_legal_hold: bool,
    s3_client: Optional[Any],
) -> Optional[str]:
    """Verify mirror receipt shape and optional live S3 state.

    Returns:
        ``None`` when verification succeeds for this entry, otherwise a stable
        reason string such as ``mirror_object_not_found``.
    """
    receipt = entry.get("mirror_receipt")
    mirror_backend = str(entry.get("mirror_backend") or "").strip().lower()
    expects_receipt = strict_mode or mirror_backend == "s3_object_lock"
    if receipt is None:
        if expects_receipt:
            return "mirror_receipt_missing"
        return None
    if not isinstance(receipt, dict):
        return "mirror_receipt_malformed"

    known_keys = {
        "bucket",
        "key",
        "version_id",
        "etag",
        "retention_mode",
        "retain_until_date",
        "legal_hold_status",
    }
    if not all(isinstance(k, str) and k in known_keys for k in receipt.keys()):
        return "mirror_receipt_malformed"
    if not _is_s3_receipt(receipt):
        return None
    if not remote_enabled:
        return None
    if s3_client is None:
        return "mirror_object_not_found"

    bucket = str(receipt["bucket"]).strip()
    key = str(receipt["key"]).strip()
    if not bucket or not key:
        return "mirror_receipt_malformed"

    head_kwargs: Dict[str, Any] = {"Bucket": bucket, "Key": key}
    if receipt.get("version_id"):
        head_kwargs["VersionId"] = receipt["version_id"]

    try:
        head = s3_client.head_object(**head_kwargs)
    except Exception:  # noqa: BLE001
        return "mirror_object_not_found"

    expected_version = receipt.get("version_id")
    if expected_version:
        actual_version = head.get("VersionId")
        if actual_version is not None and str(actual_version) != str(expected_version):
            return "mirror_version_mismatch"

    expected_etag = receipt.get("etag")
    if expected_etag:
        actual_etag = head.get("ETag")
        if _normalize_etag(actual_etag) != _normalize_etag(expected_etag):
            return "mirror_etag_mismatch"

    needs_retention = bool(receipt.get("retention_mode") or receipt.get("retain_until_date"))
    if needs_retention:
        retention_kwargs: Dict[str, Any] = {"Bucket": bucket, "Key": key}
        if receipt.get("version_id"):
            retention_kwargs["VersionId"] = receipt["version_id"]
        try:
            retention = s3_client.get_object_retention(**retention_kwargs)
            retention_obj = retention.get("Retention") or {}
        except Exception:  # noqa: BLE001
            retention_obj = {}
        if strict_s3 and not retention_obj:
            return "mirror_retention_missing"
        if receipt.get("retention_mode") and retention_obj.get("Mode") != receipt.get("retention_mode"):
            return "mirror_retention_missing"
        if receipt.get("retain_until_date") and retention_obj.get("RetainUntilDate") is None:
            return "mirror_retention_missing"

    if require_legal_hold:
        legal_hold_kwargs: Dict[str, Any] = {"Bucket": bucket, "Key": key}
        if receipt.get("version_id"):
            legal_hold_kwargs["VersionId"] = receipt["version_id"]
        try:
            legal_hold = s3_client.get_object_legal_hold(**legal_hold_kwargs)
            legal_hold_status = ((legal_hold or {}).get("LegalHold") or {}).get("Status")
        except Exception:  # noqa: BLE001
            legal_hold_status = None
        if legal_hold_status != "ON":
            return "mirror_legal_hold_missing"

    return None


def _verify_signer_metadata(entry: Dict[str, Any]) -> Optional[str]:
    """Validate signer metadata format for new witness entries.

    Legacy compatibility:
        Entries without ``signer_metadata`` are accepted.
    """
    signer_meta = entry.get("signer_metadata")
    if signer_meta is None:
        return None
    if not isinstance(signer_meta, dict):
        return "signer_metadata_malformed"

    required_str_fields = (
        "metadata_version",
        "signer_type",
        "signer_key_id",
        "signer_key_version",
        "signature_algorithm",
        "signed_at",
        "verification_policy_version",
    )
    for field in required_str_fields:
        value = signer_meta.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"signer_metadata_invalid_{field}"

    key_fingerprint = signer_meta.get("public_key_fingerprint")
    if key_fingerprint is not None and not isinstance(key_fingerprint, str):
        return "signer_metadata_invalid_public_key_fingerprint"
    return None


def _verify_anchor_receipt(entry: Dict[str, Any]) -> Optional[str]:
    """Validate optional transparency anchor backend/receipt structure."""
    has_anchor_fields = any(
        key in entry for key in ("anchor_backend", "anchor_status", "anchor_receipt")
    )
    if not has_anchor_fields:
        return None

    backend = entry.get("anchor_backend")
    if not isinstance(backend, str) or not backend.strip():
        return "anchor_backend_invalid"

    status = entry.get("anchor_status")
    valid_statuses = {"anchored", "skipped", "failed", "not_configured"}
    if not isinstance(status, str) or status not in valid_statuses:
        return "anchor_status_invalid"

    receipt = entry.get("anchor_receipt")
    if receipt is None:
        return "anchor_receipt_missing"
    if not isinstance(receipt, dict):
        return "anchor_receipt_malformed"

    required_str = {
        "backend",
        "status",
        "anchored_hash",
        "anchored_at",
        "receipt_id",
    }
    for field in required_str:
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"anchor_receipt_invalid_{field}"

    if receipt.get("backend") != backend:
        return "anchor_receipt_backend_mismatch"
    if receipt.get("status") != status:
        return "anchor_receipt_status_mismatch"

    anchored_hash = str(receipt.get("anchored_hash"))
    if not _SHA256_HEX_RE.match(anchored_hash):
        return "anchor_receipt_invalid_anchored_hash"

    receipt_payload_hash = receipt.get("receipt_payload_hash")
    if receipt_payload_hash is not None and not _SHA256_HEX_RE.match(str(receipt_payload_hash)):
        return "anchor_receipt_invalid_receipt_payload_hash"

    if receipt.get("details") is not None and not isinstance(receipt.get("details"), dict):
        return "anchor_receipt_invalid_details"

    optional_string_fields = ("receipt_location", "external_timestamp")
    for field in optional_string_fields:
        value = receipt.get(field)
        if value is not None and not isinstance(value, str):
            return f"anchor_receipt_invalid_{field}"

    return None


def verify_witness_ledger(
    entries: List[Dict[str, Any]],
    verify_signature_fn: Callable[[Dict[str, Any]], bool],
    artifact_search_roots: Optional[Sequence[Path]] = None,
    s3_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Verify witness ledger chain, payload hash, signature and metadata linkage.

    Legacy compatibility:
        Entries without ``full_payload_hash`` / ``mirror_receipt`` are treated
        as valid legacy rows.
    """
    errors: List[VerificationError] = []
    prev_hash: Optional[str] = None
    valid_entries = 0
    chain_ok = True
    signature_ok = True
    linkage_ok = True
    mirror_ok = True
    remote_enabled = _env_flag("VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE", default=False)
    strict_mode = _env_flag("VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT", default=False)
    strict_s3 = strict_mode
    require_legal_hold = _env_flag(
        "VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_REQUIRE_LEGAL_HOLD",
        default=False,
    )
    resolved_s3_client = s3_client
    if remote_enabled and resolved_s3_client is None:
        try:
            boto3 = importlib.import_module("boto3")
            resolved_s3_client = boto3.client("s3")
        except Exception:  # noqa: BLE001
            resolved_s3_client = None

    for index, entry in enumerate(entries):
        payload_hash = sha256_of_canonical_json(entry.get("decision_payload", {}))
        if payload_hash != entry.get("payload_hash"):
            errors.append(VerificationError("witness", index, "payload_hash_mismatch"))

        if entry.get("previous_hash") != prev_hash:
            chain_ok = False
            errors.append(VerificationError("witness", index, "previous_hash_mismatch"))

        if not verify_signature_fn(entry):
            signature_ok = False
            errors.append(VerificationError("witness", index, "signature_invalid"))

        linkage_result = verify_entry_artifact_linkage(
            entry,
            search_roots=artifact_search_roots,
        )
        if not linkage_result.ok:
            linkage_ok = False
            errors.append(
                VerificationError(
                    "witness",
                    index,
                    str(linkage_result.reason or "linkage_verification_failed"),
                )
            )

        mirror_error = _verify_mirror_receipt(
            entry,
            remote_enabled=remote_enabled,
            strict_mode=strict_mode,
            strict_s3=strict_s3,
            require_legal_hold=require_legal_hold,
            s3_client=resolved_s3_client,
        )
        if mirror_error:
            mirror_ok = False
            errors.append(VerificationError("witness", index, mirror_error))

        signer_meta_error = _verify_signer_metadata(entry)
        if signer_meta_error:
            errors.append(VerificationError("witness", index, signer_meta_error))

        anchor_error = _verify_anchor_receipt(entry)
        if anchor_error:
            errors.append(VerificationError("witness", index, anchor_error))

        if not any(err.index == index and err.ledger == "witness" for err in errors):
            valid_entries += 1

        prev_hash = _entry_chain_hash(entry)

    return {
        "ledger": "witness",
        "total_entries": len(entries),
        "valid_entries": valid_entries,
        "invalid_entries": len(entries) - valid_entries,
        "chain_ok": chain_ok,
        "signature_ok": signature_ok,
        "linkage_ok": linkage_ok,
        "mirror_ok": mirror_ok,
        "last_hash": prev_hash,
        "detailed_errors": [_as_dict(err) for err in errors],
        "ok": len(errors) == 0,
    }


def verify_trustlogs(
    full_log_path: Path,
    witness_entries: List[Dict[str, Any]],
    verify_signature_fn: Callable[[Dict[str, Any]], bool],
    max_entries: Optional[int] = None,
    artifact_search_roots: Optional[Sequence[Path]] = None,
) -> Dict[str, Any]:
    """Run unified verification for both full and witness ledgers."""
    full = verify_full_ledger(log_path=full_log_path, max_entries=max_entries)
    witness = verify_witness_ledger(
        entries=witness_entries,
        verify_signature_fn=verify_signature_fn,
        artifact_search_roots=artifact_search_roots,
    )

    total_entries = full["total_entries"] + witness["total_entries"]
    valid_entries = full["valid_entries"] + witness["valid_entries"]
    last_hash = witness["last_hash"] or full["last_hash"]

    return {
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "invalid_entries": total_entries - valid_entries,
        "chain_ok": full["chain_ok"] and witness["chain_ok"],
        "signature_ok": witness["signature_ok"],
        "linkage_ok": witness["linkage_ok"],
        "mirror_ok": witness["mirror_ok"],
        "last_hash": last_hash,
        "detailed_errors": full["detailed_errors"] + witness["detailed_errors"],
        "full_ledger": full,
        "witness_ledger": witness,
        "ok": full["ok"] and witness["ok"],
    }
