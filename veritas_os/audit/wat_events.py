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

_DEFAULT_WAT_METADATA_RETENTION_TTL_SECONDS = 7_776_000
_DEFAULT_WAT_EVENT_POINTER_RETENTION_TTL_SECONDS = 7_776_000
_DEFAULT_OBSERVABLE_DIGEST_RETENTION_TTL_SECONDS = 31_536_000
_DEFAULT_RETENTION_POLICY_VERSION = "wat_retention_v1"
_ALLOWED_OBSERVABLE_DIGEST_ACCESS_CLASSES: frozenset[str] = frozenset({
    "restricted",
    "privileged",
})


def _utc_now_iso_z() -> str:
    """Return current UTC timestamp in RFC3339-like ``Z`` format."""
    return format_event_ts_utc()


def format_event_ts_utc(value: Any = None) -> str:
    """Normalize event timestamps to canonical ISO-8601 UTC ``YYYY-MM-DDTHH:MM:SSZ``.

    The operator-facing v1 minimal surface requires a single stable timestamp
    representation across WAT lane storage, decide summaries, and frontend
    rendering paths. This helper centralizes the normalization rule.
    """
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            dt = datetime.now(timezone.utc)
        else:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = datetime.fromisoformat(normalized)
                dt = parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                dt = datetime.now(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _normalize_retention_boundary_details(
    details: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Normalize event details to retention boundary-safe payloads.

    Primary audit path remains lean: only metadata and event-pointer fields are
    persisted. Full observable digests are represented by
    ``observable_digest_ref`` linkage to a separate store.
    """
    raw = details if isinstance(details, dict) else {}

    metadata = raw.get("metadata")
    normalized_metadata: Dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
    for key in (
        "psid",
        "ttl_seconds",
        "mode",
        "reason",
        "request_id",
        "warning_context",
        "warning_correlation_id",
        "validation_status",
        "failure_type",
        "psid_display",
    ):
        if key in raw:
            normalized_metadata[key] = raw.get(key)
    event_lane_details = raw.get("event_lane_details")
    if isinstance(event_lane_details, dict):
        normalized_metadata["event_lane_details"] = dict(event_lane_details)

    pointers = raw.get("event_pointers")
    normalized_pointers: Dict[str, Any] = dict(pointers) if isinstance(pointers, dict) else {}

    observable_digest_ref = str(
        raw.get("observable_digest_ref") or raw.get("observable_digest") or ""
    ).strip()
    if observable_digest_ref:
        normalized_pointers["observable_digest_ref"] = observable_digest_ref

    access_class = str(raw.get("observable_digest_access_class") or "restricted").strip().lower()
    if access_class not in _ALLOWED_OBSERVABLE_DIGEST_ACCESS_CLASSES:
        raise ValueError(f"invalid_observable_digest_access_class: {access_class}")

    def _coerce_ttl(value: Any, default_value: int) -> int:
        try:
            return max(60, int(value))
        except (TypeError, ValueError):
            return default_value

    normalized_retention: Dict[str, Any] = {
        "metadata": normalized_metadata,
        "event_pointers": normalized_pointers,
        "wat_metadata_retention_ttl_seconds": _coerce_ttl(
            raw.get("wat_metadata_retention_ttl_seconds"),
            _DEFAULT_WAT_METADATA_RETENTION_TTL_SECONDS,
        ),
        "wat_event_pointer_retention_ttl_seconds": _coerce_ttl(
            raw.get("wat_event_pointer_retention_ttl_seconds"),
            _DEFAULT_WAT_EVENT_POINTER_RETENTION_TTL_SECONDS,
        ),
        "observable_digest_retention_ttl_seconds": _coerce_ttl(
            raw.get("observable_digest_retention_ttl_seconds"),
            _DEFAULT_OBSERVABLE_DIGEST_RETENTION_TTL_SECONDS,
        ),
        "observable_digest_access_class": access_class,
        "observable_digest_ref": observable_digest_ref,
        "retention_policy_version": str(
            raw.get("retention_policy_version") or _DEFAULT_RETENTION_POLICY_VERSION
        ).strip(),
        "retention_enforced_at_write": bool(raw.get("retention_enforced_at_write", True)),
    }
    assertion_failed_reasons: list[str] = []
    if normalized_retention["retention_enforced_at_write"] and not normalized_retention["retention_policy_version"]:
        assertion_failed_reasons.append("missing_retention_policy_version")
    if raw.get("observable_digest") and not normalized_retention["observable_digest_ref"]:
        assertion_failed_reasons.append("observable_digest_ref_missing")
    normalized_retention["retention_boundary_assertion"] = {
        "outcome": "passed" if not assertion_failed_reasons else "failed",
        "failed_reasons": assertion_failed_reasons,
    }
    return normalized_retention


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

    now_event_ts = _utc_now_iso_z()
    raw_details = dict(details) if isinstance(details, dict) else {}
    if str(status or "").strip().lower() == "warning":
        raw_details.setdefault("warning_context", "wat_shadow_warning")
        raw_details.setdefault("warning_correlation_id", str(uuid.uuid4()))
    normalized_details = _normalize_retention_boundary_details(raw_details)
    record: Dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "ts": now_event_ts,
        "event_ts": now_event_ts,
        "lane": "wat_shadow",
        "wat_id": str(wat_id).strip(),
        "event_type": normalized_event_type,
        "actor": str(actor or "system")[:500],
        "status": str(status or "ok")[:50],
        "details": normalized_details,
    }
    record["trustlog_anchor_ref"] = _build_anchor_reference(record)

    events_path = _resolve_events_path(path)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    with _WAT_LOCK:
        existing_events = _load_wat_events(events_path)
        previous_for_wat: Optional[Dict[str, Any]] = None
        for existing in reversed(existing_events):
            if str(existing.get("wat_id", "")).strip() == str(wat_id).strip():
                previous_for_wat = existing
                break

        previous_details = (
            previous_for_wat.get("details", {}) if isinstance(previous_for_wat, dict) else {}
        )
        if isinstance(previous_details, dict) and bool(previous_details.get("retention_enforced_at_write")):
            previous_policy_version = str(previous_details.get("retention_policy_version", "")).strip()
            current_policy_version = str(
                record["details"].get("retention_policy_version", "")
            ).strip()
            if (
                previous_policy_version
                and current_policy_version
                and previous_policy_version != current_policy_version
            ):
                raise ValueError(
                    "retention_policy_version is immutable after "
                    "retention_enforced_at_write=true"
                )

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
