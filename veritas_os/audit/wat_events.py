"""WAT shadow-lane audit event persistence helpers.

This module provides first-class storage helpers for Witness Attestation Token
(WAT) issue/validate/replay/revocation event telemetry.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from veritas_os.audit.trustlog_signed import append_signed_decision
from veritas_os.logging.paths import LOG_DIR

logger = logging.getLogger(__name__)

WAT_EVENTS_JSONL = LOG_DIR / "wat_events.jsonl"
_WAT_LOCK = threading.RLock()

SUPPORTED_WAT_EVENT_TYPES: frozenset[str] = frozenset({
    "wat_issued",
    "wat_validated",
    "wat_validation_failed",
    "wat_psid_mismatch",
    "wat_observable_missing",
    "wat_observable_digest_mismatch",
    "wat_signature_invalid",
    "wat_replay_suspected",
    "wat_revocation_pending",
    "wat_revoked_confirmed",
    "wat_partial_validation_warning",
    "wat_partial_validation_blocked",
})


def _utc_now_iso_z() -> str:
    """Return current UTC timestamp in RFC3339-like ``Z`` format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_events_path(path: Optional[Path] = None) -> Path:
    """Resolve WAT event lane storage path with optional env override."""
    if path is not None:
        return path
    env_path = (os.getenv("VERITAS_WAT_EVENTS_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return WAT_EVENTS_JSONL


def _load_wat_events(path: Optional[Path] = None) -> list[Dict[str, Any]]:
    """Load WAT event lane entries from JSONL storage."""
    events_path = _resolve_events_path(path)
    if not events_path.exists():
        return []

    entries: list[Dict[str, Any]] = []
    with events_path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
                if isinstance(row, dict):
                    entries.append(row)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed WAT event line")
    return entries


def _build_anchor_reference(event_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Write a compact witness reference to signed TrustLog when available."""
    try:
        signed = append_signed_decision(event_payload, enable_artifact_ref=True)
        return {
            "trustlog_decision_id": signed.get("decision_id"),
            "payload_hash": signed.get("payload_hash"),
            "anchor_backend": signed.get("anchor_backend"),
            "anchor_status": signed.get("anchor_status"),
        }
    except Exception as exc:  # pragma: no cover - best effort linkage
        logger.warning("WAT event TrustLog anchor append failed: %s", exc)
        return {"error": "anchor_append_failed"}


def _persist_wat_event(
    *,
    wat_id: str,
    event_type: str,
    actor: str,
    details: Optional[Dict[str, Any]] = None,
    status: str = "ok",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist a WAT audit event record.

    Args:
        wat_id: Stable WAT identifier.
        event_type: Event vocabulary item.
        actor: Initiator identity.
        details: Additional event metadata.
        status: Event outcome status label.
        path: Optional persistence path override for tests.
    """
    normalized_event_type = str(event_type or "").strip()
    if normalized_event_type not in SUPPORTED_WAT_EVENT_TYPES:
        raise ValueError(f"unsupported_wat_event_type: {normalized_event_type}")

    record: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "ts": _utc_now_iso_z(),
        "lane": "wat_shadow",
        "wat_id": str(wat_id).strip(),
        "event_type": normalized_event_type,
        "actor": str(actor or "system")[:500],
        "status": str(status or "ok")[:50],
        "details": details or {},
    }
    record["trustlog_anchor_ref"] = _build_anchor_reference(record)

    events_path = _resolve_events_path(path)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    with _WAT_LOCK:
        with events_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(record, ensure_ascii=False) + "\n")
            file_obj.flush()
            os.fsync(file_obj.fileno())

    return record


def persist_wat_issuance_event(
    *,
    wat_id: str,
    actor: str,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist ``wat_issued`` event in the WAT shadow event lane."""
    return _persist_wat_event(
        wat_id=wat_id,
        event_type="wat_issued",
        actor=actor,
        details=details,
        path=path,
    )


def persist_wat_validation_event(
    *,
    wat_id: str,
    actor: str,
    event_type: str = "wat_validated",
    details: Optional[Dict[str, Any]] = None,
    status: str = "ok",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist WAT validation result events for shadow validation workflows."""
    return _persist_wat_event(
        wat_id=wat_id,
        event_type=event_type,
        actor=actor,
        details=details,
        status=status,
        path=path,
    )


def persist_wat_replay_event(
    *,
    wat_id: str,
    actor: str,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist ``wat_replay_suspected`` event."""
    return _persist_wat_event(
        wat_id=wat_id,
        event_type="wat_replay_suspected",
        actor=actor,
        details=details,
        status="warning",
        path=path,
    )


def persist_wat_revocation_event(
    *,
    wat_id: str,
    actor: str,
    confirmed: bool,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist WAT revocation transition event."""
    return _persist_wat_event(
        wat_id=wat_id,
        event_type="wat_revoked_confirmed" if confirmed else "wat_revocation_pending",
        actor=actor,
        details=details,
        status="ok" if confirmed else "pending",
        path=path,
    )


def get_wat_event(wat_id: str, *, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return the latest event for a WAT id, if present."""
    target = str(wat_id or "").strip()
    if not target:
        return None
    with _WAT_LOCK:
        events = _load_wat_events(path)
    for event in reversed(events):
        if str(event.get("wat_id", "")).strip() == target:
            return event
    return None


def derive_latest_revocation_state(
    wat_id: str,
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Derive structured local revocation state from latest WAT lane event.

    Returns a mapping compatible with ``validate_local(revocation_state=...)``:
    ``status`` is always one of ``active``, ``revoked_pending``,
    ``revoked_confirmed``.
    """
    target = str(wat_id or "").strip()
    if not target:
        return {"status": "active", "source": "wat_events"}

    timeline = list_wat_events(wat_id=target, limit=500, path=path)
    for event in timeline:
        event_type = str(event.get("event_type", "")).strip()
        if event_type == "wat_revoked_confirmed":
            return {
                "status": "revoked_confirmed",
                "source": "wat_events",
                "event_type": event_type,
                "event_id": event.get("event_id"),
                "ts": event.get("ts"),
            }
        if event_type == "wat_revocation_pending":
            return {
                "status": "revoked_pending",
                "source": "wat_events",
                "event_type": event_type,
                "event_id": event.get("event_id"),
                "ts": event.get("ts"),
            }
    return {"status": "active", "source": "wat_events"}


def list_wat_events(
    *,
    wat_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    path: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    """List WAT event lane entries with optional filters."""
    safe_limit = max(1, min(int(limit), 500))
    with _WAT_LOCK:
        events = _load_wat_events(path)

    filtered = events
    if wat_id:
        needle = str(wat_id).strip()
        filtered = [item for item in filtered if str(item.get("wat_id", "")).strip() == needle]
    if event_type:
        evt = str(event_type).strip()
        filtered = [item for item in filtered if str(item.get("event_type", "")).strip() == evt]

    return list(reversed(filtered))[:safe_limit]


def prune_wat_events(*, retention_days: int = 90, path: Optional[Path] = None) -> int:
    """Delete old WAT events beyond retention period and return deleted count."""
    days = max(1, min(int(retention_days), 3650))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events_path = _resolve_events_path(path)
    with _WAT_LOCK:
        events = _load_wat_events(events_path)
        kept: list[Dict[str, Any]] = []
        deleted = 0
        for row in events:
            timestamp = str(row.get("ts") or "")
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                kept.append(row)
                continue
            if parsed < cutoff:
                deleted += 1
            else:
                kept.append(row)

        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("w", encoding="utf-8") as file_obj:
            for row in kept:
                file_obj.write(json.dumps(row, ensure_ascii=False) + "\n")
            file_obj.flush()
            os.fsync(file_obj.fileno())

    return deleted
