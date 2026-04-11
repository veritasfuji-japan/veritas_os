"""Signed, append-only TrustLog utilities.

This module provides cryptographic integrity and authenticity checks for
structured decision audit logs.

Design (post-compaction):
    The signed TrustLog stores a *lightweight audit summary* per decision,
    not the full decision payload.  Full payloads are persisted separately
    in ``decide_*.json`` / ``trust_log.jsonl`` (encrypted).  Each signed
    entry carries:

    - ``decision_payload``: compact summary (see :func:`build_trustlog_summary`)
    - ``payload_hash``: SHA-256 of the *compact summary* (chain-verified)
    - ``full_payload_hash``: SHA-256 of the *original full payload* so that
      an auditor can correlate the summary back to the full artifact on disk.
    - ``artifact_ref`` (optional): structured locator metadata that helps
      verifiers resolve the exact full artifact and recompute linkage hashes.

    This keeps individual JSONL lines small while preserving cryptographic
    traceability to the original data.
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
from veritas_os.audit.storage_mirror import build_storage_mirror
from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json
from veritas_os.audit.trustlog_verify import verify_witness_ledger
from veritas_os.security.signing import (
    Signer,
    build_trustlog_signer,
    store_keypair,
)

SIGNED_TRUSTLOG_JSONL = LOG_DIR / "trustlog.jsonl"
SIGNED_TRUSTLOG_KEYS = LOG_DIR / "keys"
PRIVATE_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_private.key"
PUBLIC_KEY_PATH = SIGNED_TRUSTLOG_KEYS / "trustlog_ed25519_public.key"

_lock = threading.RLock()
_logger = logging.getLogger(__name__)
TRUSTLOG_SIGNER_METADATA_VERSION = "v2"
TRUSTLOG_VERIFICATION_POLICY_VERSION = "trustlog_witness_v2"


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
    """Return whether WORM mirror failures must abort TrustLog writes.

    When the runtime posture is *secure* or *prod* and no explicit env
    var is set, the posture-derived default is used (True).
    """
    raw = os.getenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    # Fall back to posture-derived default.
    try:
        from veritas_os.core.posture import get_active_posture
        return get_active_posture().trustlog_worm_hard_fail
    except Exception:
        return False


def _transparency_log_path() -> Optional[Path]:
    """Resolve optional transparency log destination for TrustLog anchors."""
    anchor_path = os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "").strip()
    if not anchor_path:
        return None
    return Path(anchor_path)


def _transparency_anchor_backend() -> str:
    """Resolve transparency anchor backend from environment."""
    raw = (os.getenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND") or "local").strip().lower()
    if raw in {"", "local", "file"}:
        return "local"
    if raw in {"none", "noop", "no_op"}:
        return "noop"
    return raw


def _transparency_required_enabled() -> bool:
    """Return whether transparency anchoring failures must abort writes.

    When the runtime posture is *secure* or *prod* and no explicit env
    var is set, the posture-derived default is used (True).
    """
    raw = os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    try:
        from veritas_os.core.posture import get_active_posture
        return get_active_posture().trustlog_transparency_required
    except Exception:
        return False


def _append_line(path: Path, line: str) -> None:
    """Append a line to ``path``, creating parent directories when required.

    Uses ``fsync`` to ensure durability — matching the main TrustLog's
    write-ahead guarantee so that signed entries survive process crashes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line)
        file.flush()
        os.fsync(file.fileno())


def _mirror_to_worm(line: str) -> Dict[str, Any]:
    """Best-effort append using the configured mirror backend."""
    try:
        mirror_backend = build_storage_mirror(append_fn=_append_line)
    except (ValueError, TypeError) as exc:
        return {
            "configured": True,
            "ok": False,
            "backend": "invalid",
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    result = mirror_backend.append_line(line)
    if not result.get("ok"):
        _logger.warning(
            "WORM mirror write failed (backend=%s): %s",
            result.get("backend"),
            result.get("error", "unknown_error"),
        )
    return result


def _append_transparency_anchor(entry_hash: str) -> Dict[str, Any]:
    """Best-effort append of the latest chain hash to a transparency log.

    The transparency log can be a local spool file that is shipped to an
    external append-only system by infrastructure.
    """
    backend = _transparency_anchor_backend()
    if backend == "noop":
        return {"configured": True, "ok": True, "backend": "noop", "path": None}
    if backend != "local":
        return {
            "configured": True,
            "ok": False,
            "backend": "invalid",
            "path": None,
            "error": (
                "ValueError: Unsupported VERITAS_TRUSTLOG_ANCHOR_BACKEND. "
                "Expected 'local' or 'noop'."
            ),
        }

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
        _logger.warning(
            "Transparency anchor write failed (path=%s): %s: %s",
            path, exc.__class__.__name__, exc,
        )
        return {
            "configured": True,
            "ok": False,
            "path": str(path),
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    return {
        "configured": True,
        "ok": True,
        "backend": "local",
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


def _resolve_signer(*, ensure_local_keys: bool = False) -> Signer:
    """Resolve active TrustLog signer backend.

    Environment:
        - VERITAS_TRUSTLOG_SIGNER_BACKEND=file|aws_kms (default: file)
        - VERITAS_TRUSTLOG_KMS_KEY_ID=... (required for aws_kms)
    """
    return build_trustlog_signer(
        private_key_path=PRIVATE_KEY_PATH,
        public_key_path=PUBLIC_KEY_PATH,
        ensure_local_keys=ensure_local_keys,
    )


def _ensure_signing_keys() -> None:
    """Backward-compatible shim for tests and legacy call sites.

    Historically this module exposed ``_ensure_signing_keys`` and unit tests
    monkeypatched it. The signer abstraction now owns key bootstrap logic, but
    this shim is intentionally retained to preserve compatibility.
    """
    _resolve_signer(ensure_local_keys=True)


def _resolve_signer_for_entry(entry: Dict[str, Any]) -> Signer:
    """Resolve signer for a persisted TrustLog entry.

    The signer is selected from entry metadata first so mixed-backend
    historical logs remain verifiable after backend migrations.
    """
    signer_meta = entry.get("signer_metadata")
    signer_type = str(entry.get("signer_type", "")).strip().lower()
    signer_key_id = str(entry.get("signer_key_id", "")).strip()
    if isinstance(signer_meta, dict):
        signer_type = str(signer_meta.get("signer_type", signer_type)).strip().lower()
        signer_key_id = str(signer_meta.get("signer_key_id", signer_key_id)).strip()
    if signer_type:
        return build_trustlog_signer(
            private_key_path=PRIVATE_KEY_PATH,
            public_key_path=PUBLIC_KEY_PATH,
            backend=signer_type,
            kms_key_id=signer_key_id or None,
        )
    return _resolve_signer()


def _build_signer_metadata(signer: Signer, *, signed_at: str) -> Dict[str, Any]:
    """Build normalized signer metadata for long-term witness verification.

    Normalization rules:
        - ``signer_key_version`` may be ``unknown`` for backends like AWS KMS
          that do not expose per-sign operation key versions.
        - ``public_key_fingerprint`` can be ``None`` when a backend cannot
          provide a public key during write-time.
    """
    public_key_fp = signer.public_key_fingerprint()
    return {
        "metadata_version": TRUSTLOG_SIGNER_METADATA_VERSION,
        "signer_type": signer.signer_type,
        "signer_key_id": signer.signer_key_id(),
        "signer_key_version": signer.signer_key_version(),
        "signature_algorithm": signer.signature_algorithm(),
        "public_key_fingerprint": public_key_fp,
        "signed_at": signed_at,
        "verification_policy_version": TRUSTLOG_VERIFICATION_POLICY_VERSION,
        "key_version_normalized": signer.signer_key_version() == "unknown",
        "fingerprint_missing": public_key_fp is None,
    }


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
                        _logger.warning(
                            "Skipping corrupt trailing entry in signed TrustLog at %s",
                            path,
                        )
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


# ---------------------------------------------------------------------------
# TrustLog payload compaction
# ---------------------------------------------------------------------------

#: Maximum allowed size (bytes) for a single serialized TrustLog entry line.
#: Entries exceeding this threshold trigger an ``_OVERSIZED_MARKER`` warning
#: in the logged payload so that operators can investigate without silent
#: data loss.
MAX_ENTRY_LINE_BYTES: int = 32_768  # 32 KiB — generous for a summary line

_OVERSIZED_MARKER = "__trustlog_oversized__"

#: Allowlist of top-level keys that are copied verbatim from the full
#: decision payload into the TrustLog summary.  Anything not listed here
#: is dropped.  This is deliberately conservative — add keys only when
#: they are essential for audit-chain verification or operational triage.
_SUMMARY_ALLOWLIST: frozenset[str] = frozenset({
    # Identity & linkage
    "request_id",
    "created_at",
    "decision_id",
    "context_user_id",
    # Hash-chain fields (set by append_trust_log before reaching here)
    "sha256",
    "sha256_prev",
    # Decision outcome
    "decision_status",
    "chosen_title",
    "rejection_reason",
    # Risk & scoring
    "telos_score",
    "gate_risk",
    "gate_total",
    "gate_status",
    # Policy
    "fast_mode",
    "plan_steps",
    "mem_hits",
    "web_hits",
    # Critique
    "critique_ok",
    "critique_mode",
    "critique_reason",
})

#: Keys inside the full payload whose *scalar* value is extracted for the
#: summary even though the parent object is excluded.  Format:
#: ``(dotted_path, summary_key)``.
_NESTED_SCALAR_EXTRACTS: tuple[tuple[str, str], ...] = (
    ("fuji.status", "fuji_status"),
    ("fuji.risk", "fuji_risk"),
    ("chosen.title", "chosen_title"),
)


def _deep_get(d: Dict[str, Any], dotted: str) -> Any:
    """Resolve a dotted key path against nested dicts, returning *None* on miss."""
    parts = dotted.split(".")
    cur: Any = d
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def build_trustlog_summary(full_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact audit summary from a full decision payload.

    The summary uses an **allowlist** approach: only keys in
    ``_SUMMARY_ALLOWLIST`` are kept.  A handful of nested scalars (e.g.
    ``fuji.status``) are promoted to top-level keys so that the summary
    remains flat and small.

    The caller is responsible for computing ``full_payload_hash`` on the
    *original* payload and attaching it to the signed entry separately.

    Returns:
        A new dict suitable for ``decision_payload`` in the signed TrustLog.
    """
    summary: Dict[str, Any] = {}

    # 1. Copy allowlisted top-level scalars
    for key in _SUMMARY_ALLOWLIST:
        if key in full_payload:
            summary[key] = full_payload[key]

    # 2. Extract selected nested scalars
    for dotted, target_key in _NESTED_SCALAR_EXTRACTS:
        if target_key not in summary:
            val = _deep_get(full_payload, dotted)
            if val is not None:
                summary[target_key] = val

    # 3. Ensure chosen_title from chosen dict if not already present
    if "chosen_title" not in summary and isinstance(full_payload.get("chosen"), dict):
        summary["chosen_title"] = full_payload["chosen"].get("title")

    return summary


def _enforce_entry_size(
    entry: Dict[str, Any],
    signer: Optional[Signer] = None,
) -> Dict[str, Any]:
    """Ensure the serialized entry does not exceed ``MAX_ENTRY_LINE_BYTES``.

    If the entry is oversized, the ``decision_payload`` is replaced with
    a minimal stub that preserves the ``request_id`` and an explicit
    ``__trustlog_oversized__`` marker so the anomaly is auditable.

    When the entry is oversized, the ``payload_hash`` and ``signature``
    are recalculated against the stub so that :func:`verify_trustlog_chain`
    can still validate the on-disk entry without false-positive mismatches.
    The ``original_payload_hash`` field in the stub preserves the link to
    the original compact summary.

    Returns:
        The (possibly replaced) entry dict.
    """
    active_signer = signer if signer is not None else _resolve_signer(ensure_local_keys=True)
    line = json.dumps(entry, ensure_ascii=False)
    if len(line.encode("utf-8")) <= MAX_ENTRY_LINE_BYTES:
        return entry

    _logger.warning(
        "Signed TrustLog entry exceeds %d bytes (%d actual); "
        "replacing decision_payload with oversized stub for request_id=%s",
        MAX_ENTRY_LINE_BYTES,
        len(line.encode("utf-8")),
        (entry.get("decision_payload") or {}).get("request_id", "?"),
    )

    stub_payload: Dict[str, Any] = {
        "request_id": (entry.get("decision_payload") or {}).get("request_id"),
        _OVERSIZED_MARKER: True,
        "original_payload_hash": entry.get("payload_hash"),
    }
    entry = dict(entry)
    entry["decision_payload"] = stub_payload

    # Recalculate payload_hash and signature so verify_trustlog_chain
    # can validate the on-disk entry without false-positive mismatches.
    entry["payload_hash"] = sha256_of_canonical_json(stub_payload)
    try:
        entry["signature"] = active_signer.sign_payload_hash(entry["payload_hash"])
    except Exception:
        _logger.warning(
            "Failed to re-sign oversized stub entry; signature will be stale",
            exc_info=True,
        )

    return entry




def _build_artifact_reference(decision_payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build structured artifact linkage metadata for full-ledger payloads.

    Newer witness entries can carry this manifest so verifiers resolve the
    exact encrypted full-ledger row and recompute ``full_payload_hash`` from
    canonical JSON content.

    Returns ``None`` for legacy/custom call sites where no stable locator is
    available (for example direct tests that call ``append_signed_decision``
    without trust-log ``sha256`` fields).
    """
    full_sha = decision_payload.get("sha256")
    if not isinstance(full_sha, str) or not full_sha.strip():
        return None
    locator = f"sha256:{full_sha.strip()}"

    return {
        "artifact_ref": "trustlog_full_payload",
        "artifact_type": "trust_log_entry",
        "artifact_storage_backend": "trustlog_full_ledger",
        "artifact_locator": locator,
        "artifact_hash_algorithm": "sha256_canonical_json",
    }

def append_signed_decision(
    decision_payload: Dict[str, Any],
    *,
    enable_artifact_ref: bool = False,
) -> Dict[str, Any]:
    """Append a signed decision entry to append-only TrustLog JSONL.

    Since the compaction redesign, ``decision_payload`` written to disk is
    the *compact summary* produced by :func:`build_trustlog_summary`.  The
    full payload hash is stored in ``full_payload_hash`` for cross-reference.

    Args:
        decision_payload: Full payload object from the decision pipeline.
        enable_artifact_ref: When ``True``, attach structured ``artifact_ref``
            metadata if a stable full-ledger locator is available. This is
            enabled by the full TrustLog integration path.

    Raises:
        SignedTrustLogWriteError: If signing/write fails due to expected
            runtime errors (filesystem, serialization, or value issues).
    """
    try:
        with _lock:
            signer = _resolve_signer(ensure_local_keys=True)
            last_entry = _read_last_entry(SIGNED_TRUSTLOG_JSONL)
            previous_hash = _entry_chain_hash(last_entry) if last_entry else None

            # Compute hash of the *full* payload for cross-reference,
            # then compact to a lightweight summary for on-disk storage.
            full_payload_hash = sha256_of_canonical_json(decision_payload)
            compact_payload = build_trustlog_summary(decision_payload)

            payload_hash = sha256_of_canonical_json(compact_payload)
            signature = signer.sign_payload_hash(payload_hash)
            signed_at = _utc_now_iso8601()
            signer_metadata = _build_signer_metadata(signer, signed_at=signed_at)

            entry = {
                "decision_id": _uuid7(),
                "timestamp": signed_at,
                "previous_hash": previous_hash,
                "decision_payload": compact_payload,
                "payload_hash": payload_hash,
                "full_payload_hash": full_payload_hash,
                "signature": signature,
                "signer_type": signer.signer_type,
                "signer_key_id": signer.signer_key_id(),
                "signer_metadata": signer_metadata,
            }
            if enable_artifact_ref:
                artifact_ref = _build_artifact_reference(decision_payload)
                if artifact_ref is not None:
                    entry["artifact_ref"] = artifact_ref

            # Enforce maximum entry size before writing
            entry = _enforce_entry_size(entry, signer)

            line = json.dumps(entry, ensure_ascii=False) + "\n"
            _append_line(SIGNED_TRUSTLOG_JSONL, line)
            mirror = _mirror_to_worm(line)
            if _worm_hard_fail_enabled() and mirror.get("configured") and not mirror.get("ok"):
                raise SignedTrustLogWriteError("worm_mirror_write_failed")
            entry["worm_mirror"] = mirror
            entry["mirror_backend"] = mirror.get("backend")
            entry["mirror_receipt"] = (
                {
                    key: mirror.get(key)
                    for key in (
                        "bucket",
                        "key",
                        "version_id",
                        "etag",
                        "retention_mode",
                        "retain_until_date",
                    )
                    if mirror.get(key) is not None
                }
                if mirror.get("ok")
                else None
            )

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
    try:
        signer = _resolve_signer_for_entry(entry)
        return signer.verify_payload_signature(
            payload_hash=str(entry["payload_hash"]),
            signature_b64=str(entry["signature"]),
        )
    except Exception:  # noqa: BLE001
        # Malformed signatures (bad base64, wrong length, etc.) are treated
        # as verification failures rather than propagating as crashes.
        return False


def verify_trustlog_chain(path: Optional[Path] = None) -> Dict[str, Any]:
    """Verify the full signed TrustLog chain and per-entry signatures.

    The response includes optional WORM mirror status and key metadata when
    available, so operators can schedule this function as a periodic integrity
    job and alert on any drift.
    """
    entries = _read_all_entries(path)
    witness_result = verify_witness_ledger(entries=entries, verify_signature_fn=verify_signature)

    selected_mirror_backend = os.getenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local").strip().lower()
    worm_path = _worm_mirror_path() if selected_mirror_backend == "local" else None
    s3_bucket = os.getenv("VERITAS_TRUSTLOG_S3_BUCKET", "").strip()
    mirror_configured = worm_path is not None if selected_mirror_backend == "local" else bool(s3_bucket)
    worm_status: Dict[str, Any] = {
        "backend": selected_mirror_backend or "local",
        "configured": mirror_configured,
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

    key_meta: Dict[str, Any] = {
        "public_key_present": PUBLIC_KEY_PATH.exists(),
    }
    try:
        signer = _resolve_signer()
        key_meta["signer_type"] = signer.signer_type
        key_meta["signer_key_id"] = signer.signer_key_id()
    except Exception:
        _logger.warning("Could not resolve TrustLog signer metadata", exc_info=True)

    issues = [
        {"index": err["index"], "reason": err["reason"]}
        for err in witness_result["detailed_errors"]
    ]

    return {
        "ok": witness_result["ok"],
        "entries_checked": witness_result["total_entries"],
        "issues": issues,
        "worm_mirror": worm_status,
        "transparency_anchor": transparency_status,
        "key_management": key_meta,
        "summary": {
            "total_entries": witness_result["total_entries"],
            "valid_entries": witness_result["valid_entries"],
            "invalid_entries": witness_result["invalid_entries"],
            "chain_ok": witness_result["chain_ok"],
            "signature_ok": witness_result["signature_ok"],
            "linkage_ok": witness_result["linkage_ok"],
            "mirror_ok": witness_result["mirror_ok"],
            "last_hash": witness_result["last_hash"],
            "detailed_errors": witness_result["detailed_errors"],
        },
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
