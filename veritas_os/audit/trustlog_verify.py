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


def _verify_mirror_receipt(entry: Dict[str, Any]) -> bool:
    receipt = entry.get("mirror_receipt")
    if receipt is None:
        return True
    if not isinstance(receipt, dict):
        return False
    known_keys = {
        "bucket",
        "key",
        "version_id",
        "etag",
        "retention_mode",
        "retain_until_date",
    }
    return all(isinstance(k, str) and k in known_keys for k in receipt.keys())


def verify_witness_ledger(
    entries: List[Dict[str, Any]],
    verify_signature_fn: Callable[[Dict[str, Any]], bool],
    artifact_search_roots: Optional[Sequence[Path]] = None,
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

        if not _verify_mirror_receipt(entry):
            mirror_ok = False
            errors.append(VerificationError("witness", index, "mirror_receipt_invalid"))

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
