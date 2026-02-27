"""Signed, append-only TrustLog utilities.

This module provides cryptographic integrity and authenticity checks for
structured decision audit logs.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from veritas_os.logging.paths import LOG_DIR
from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json
from veritas_os.security.signing import (
    sign_payload_hash,
    store_keypair,
    verify_payload_signature,
)

SIGNED_TRUSTLOG_JSONL = LOG_DIR / "trustlog.jsonl"
SIGNED_TRUSTLOG_KEYS = LOG_DIR / "keys"
PRIVATE_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_private.key"
PUBLIC_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_public.key"

_lock = threading.RLock()


@dataclass
class TrustLogIssue:
    """Represents a detected chain or signature integrity issue."""

    index: int
    reason: str



def _uuid7() -> str:
    """Generate a UUIDv7-compatible identifier.

    Uses 48-bit Unix epoch milliseconds and random bits per RFC 9562 layout.
    """
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


def _ensure_signing_keys() -> None:
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    store_keypair(PRIVATE_KEY_PATH, PUBLIC_KEY_PATH)


def _entry_chain_hash(entry: Dict[str, Any]) -> str:
    return sha256_hex(canonical_json_dumps(entry))


def _read_all_entries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = path or SIGNED_TRUSTLOG_JSONL
    if not path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def append_signed_decision(decision_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Append a signed decision entry to append-only TrustLog JSONL."""
    _ensure_signing_keys()
    with _lock:
        entries = _read_all_entries(SIGNED_TRUSTLOG_JSONL)
        previous_hash = _entry_chain_hash(entries[-1]) if entries else None
        payload_hash = sha256_of_canonical_json(decision_payload)
        signature = sign_payload_hash(payload_hash, PRIVATE_KEY_PATH)

        entry = {
            "decision_id": _uuid7(),
            "timestamp": _utc_now_iso8601(),
            "previous_hash": previous_hash,
            "decision_payload": decision_payload,
            "payload_hash": payload_hash,
            "signature": signature,
        }

        SIGNED_TRUSTLOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with SIGNED_TRUSTLOG_JSONL.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def verify_signature(entry: Dict[str, Any]) -> bool:
    """Verify signature validity of one TrustLog entry."""
    required = {"payload_hash", "signature"}
    if not required.issubset(entry):
        return False
    if not PUBLIC_KEY_PATH.exists():
        return False
    return verify_payload_signature(
        payload_hash=str(entry["payload_hash"]),
        signature_b64=str(entry["signature"]),
        public_key_path=PUBLIC_KEY_PATH,
    )


def verify_trustlog_chain(path: Optional[Path] = None) -> Dict[str, Any]:
    """Verify the full signed TrustLog chain and per-entry signatures."""
    entries = _read_all_entries(path)
    issues: List[TrustLogIssue] = []
    previous_hash: Optional[str] = None

    for index, entry in enumerate(entries):
        payload_hash = sha256_of_canonical_json(entry.get("decision_payload", {}))
        if payload_hash != entry.get("payload_hash"):
            issues.append(TrustLogIssue(index=index, reason="payload_hash_mismatch"))

        if entry.get("previous_hash") != previous_hash:
            issues.append(TrustLogIssue(index=index, reason="previous_hash_mismatch"))

        if not verify_signature(entry):
            issues.append(TrustLogIssue(index=index, reason="signature_invalid"))

        previous_hash = _entry_chain_hash(entry)

    return {
        "ok": len(issues) == 0,
        "entries_checked": len(entries),
        "issues": [issue.__dict__ for issue in issues],
    }


def detect_tampering(path: Optional[Path] = None) -> Dict[str, Any]:
    """Detect any tampering signs in the signed TrustLog chain."""
    result = verify_trustlog_chain(path=path)
    return {
        "tampered": not result["ok"],
        "entries_checked": result["entries_checked"],
        "issues": result["issues"],
    }


def export_signed_trustlog(path: Optional[Path] = None) -> Dict[str, Any]:
    """Export all signed TrustLog entries and public verification metadata."""
    entries = _read_all_entries(path)
    return {
        "entries": entries,
        "count": len(entries),
        "public_key_path": str(PUBLIC_KEY_PATH),
    }
