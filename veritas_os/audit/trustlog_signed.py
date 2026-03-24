"""Signed, append-only TrustLog utilities.

This module provides cryptographic integrity and authenticity checks for
structured decision audit logs.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from veritas_os.logging.paths import LOG_DIR
from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json
from veritas_os.security.signing import (
    public_key_fingerprint,
    sign_payload_hash,
    store_keypair,
    verify_payload_signature,
)

SIGNED_TRUSTLOG_JSONL = LOG_DIR / "trustlog.jsonl"
SIGNED_TRUSTLOG_KEYS = LOG_DIR / "keys"
PRIVATE_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_private.key"
PUBLIC_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_public.key"

_lock = threading.RLock()
_logger = logging.getLogger(__name__)


class SignedTrustLogWriteError(RuntimeError):
    """Raised when signed TrustLog append fails for expected runtime reasons."""


def _worm_mirror_path() -> Optional[Path]:
    """Resolve optional immutable mirror destination for TrustLog JSONL.

    The path is configured via ``VERITAS_TRUSTLOG_WORM_MIRROR_PATH`` and is
    intended to point to a WORM/object-lock mounted location managed by
    infrastructure.
    """
    mirror = os.getenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "").strip()
    if not mirror:
        return None
    return Path(mirror)


def _worm_hard_fail_enabled() -> bool:
    """Return whether WORM mirror failures must abort TrustLog writes."""
    raw = (os.getenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _transparency_log_path() -> Optional[Path]:
    """Resolve optional transparency log destination for TrustLog anchors."""
    anchor_path = os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "").strip()
    if not anchor_path:
        return None
    return Path(anchor_path)


def _transparency_required_enabled() -> bool:
    """Return whether transparency anchoring failures must abort writes."""
    raw = (os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _append_line(path: Path, line: str) -> None:
    """Append a line to ``path``, creating parent directories when required."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line)


def _mirror_to_worm(line: str) -> Dict[str, Any]:
    """Best-effort append to configured WORM mirror destination."""
    path = _worm_mirror_path()
    if path is None:
        return {"configured": False, "ok": False, "path": None}

    try:
        _append_line(path, line)
    except OSError as exc:
        return {
            "configured": True,
            "ok": False,
            "path": str(path),
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    return {"configured": True, "ok": True, "path": str(path)}


def _append_transparency_anchor(entry_hash: str) -> Dict[str, Any]:
    """Best-effort append of the latest chain hash to a transparency log.

    The transparency log can be a local spool file that is shipped to an
    external append-only system by infrastructure.
    """
    path = _transparency_log_path()
    if path is None:
        return {"configured": False, "ok": False, "path": None}

    payload = {
        "timestamp": _utc_now_iso8601(),
        "entry_hash": entry_hash,
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        _append_line(path, line)
    except OSError as exc:
        return {
            "configured": True,
            "ok": False,
            "path": str(path),
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    return {
        "configured": True,
        "ok": True,
        "path": str(path),
        "entry_hash": entry_hash,
    }


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


def _read_last_entry(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """最終エントリのみを読み取る（O(1) に近い性能）。"""
    path = path or SIGNED_TRUSTLOG_JSONL
    if not path.exists():
        return None
    chunk_size = 65536
    with path.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        if file_size == 0:
            return None
        pos = file_size
        buf = b""
        while pos > 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + buf
            lines = buf.splitlines()
            # 末尾から非空行を探す
            for raw in reversed(lines):
                raw = raw.strip()
                if raw:
                    try:
                        return json.loads(raw.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
            # まだ非空行が見つからなければ、さらに読み戻す
    return None


def _read_all_entries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = path or SIGNED_TRUSTLOG_JSONL
    if not path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _logger.warning(
                    "Skipping corrupt TrustLog entry at %s line %d: %s",
                    path,
                    line_no,
                    exc,
                )
    return entries


def append_signed_decision(decision_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Append a signed decision entry to append-only TrustLog JSONL.

    Raises:
        SignedTrustLogWriteError: If signing/write fails due to expected
            runtime errors (filesystem, serialization, or value issues).
    """
    try:
        _ensure_signing_keys()
        with _lock:
            last_entry = _read_last_entry(SIGNED_TRUSTLOG_JSONL)
            previous_hash = _entry_chain_hash(last_entry) if last_entry else None
            payload_hash = sha256_of_canonical_json(decision_payload)
            signature = sign_payload_hash(payload_hash, PRIVATE_KEY_PATH)

            entry = {
                "decision_id": _uuid7(),
                "timestamp": _utc_now_iso8601(),
                "previous_hash": previous_hash,
                "decision_payload": decision_payload,
                "payload_hash": payload_hash,
                "signature": signature,
                "signature_key_fingerprint": public_key_fingerprint(PUBLIC_KEY_PATH),
            }

            line = json.dumps(entry, ensure_ascii=False) + "\n"
            _append_line(SIGNED_TRUSTLOG_JSONL, line)
            mirror = _mirror_to_worm(line)
            if _worm_hard_fail_enabled() and mirror.get("configured") and not mirror.get("ok"):
                raise SignedTrustLogWriteError("worm_mirror_write_failed")
            entry["worm_mirror"] = mirror

            transparency_anchor = _append_transparency_anchor(_entry_chain_hash(entry))
            if (
                _transparency_required_enabled()
                and transparency_anchor.get("configured")
                and not transparency_anchor.get("ok")
            ):
                raise SignedTrustLogWriteError("transparency_anchor_write_failed")
            entry["transparency_anchor"] = transparency_anchor

        return entry
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise SignedTrustLogWriteError("signed trust log append failed") from exc


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
    """Verify the full signed TrustLog chain and per-entry signatures.

    The response includes optional WORM mirror status and key metadata when
    available, so operators can schedule this function as a periodic integrity
    job and alert on any drift.
    """
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

    worm_path = _worm_mirror_path()
    worm_status: Dict[str, Any] = {
        "configured": worm_path is not None,
        "hard_fail": _worm_hard_fail_enabled(),
    }
    if worm_path is not None:
        worm_status.update({
            "path": str(worm_path),
            "exists": worm_path.exists(),
            "entries": len(_read_all_entries(worm_path)) if worm_path.exists() else 0,
        })

    transparency_path = _transparency_log_path()
    transparency_status: Dict[str, Any] = {
        "configured": transparency_path is not None,
        "required": _transparency_required_enabled(),
    }
    if transparency_path is not None:
        transparency_status.update({
            "path": str(transparency_path),
            "exists": transparency_path.exists(),
        })

    key_meta: Dict[str, Any] = {"public_key_present": PUBLIC_KEY_PATH.exists()}
    if PUBLIC_KEY_PATH.exists():
        key_meta["fingerprint"] = public_key_fingerprint(PUBLIC_KEY_PATH)

    return {
        "ok": len(issues) == 0,
        "entries_checked": len(entries),
        "issues": [issue.__dict__ for issue in issues],
        "worm_mirror": worm_status,
        "transparency_anchor": transparency_status,
        "key_management": key_meta,
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
