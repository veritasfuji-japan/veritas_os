"""Lifecycle helpers for MemoryStore records.

This module isolates metadata normalization and expiry/legal-hold decisions
from ``core.memory`` so that lifecycle policy changes can be tested and
reviewed independently.
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Callable, Dict, Optional, Set


def parse_expires_at(expires_at: Any) -> Optional[str]:
    """Normalize ``expires_at`` into a UTC ISO-8601 string or ``None``."""
    if expires_at in (None, ""):
        return None

    if isinstance(expires_at, (int, float)):
        dt = datetime.fromtimestamp(float(expires_at), tz=timezone.utc)
        return dt.isoformat()

    if isinstance(expires_at, str):
        raw = expires_at.strip()
        if not raw:
            return None
        iso = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    return None


def normalize_lifecycle(
    value: Any,
    default_retention_class: str,
    allowed_retention_classes: Set[str],
    parse_expires_at_fn: Callable[[Any], Optional[str]],
) -> Any:
    """Attach normalized lifecycle metadata to memory-style dict payloads."""
    if not isinstance(value, dict):
        return value

    lifecycle_target_keys = {"text", "kind", "tags", "meta"}
    if not any(key in value for key in lifecycle_target_keys):
        return value

    normalized = dict(value)
    meta = dict(normalized.get("meta") or {})

    retention_class = str(
        meta.get("retention_class") or default_retention_class
    ).strip().lower()
    if retention_class not in allowed_retention_classes:
        retention_class = default_retention_class

    legal_hold = bool(meta.get("legal_hold", False))
    normalized_expires_at = parse_expires_at_fn(meta.get("expires_at"))

    meta["retention_class"] = retention_class
    meta["legal_hold"] = legal_hold
    meta["expires_at"] = normalized_expires_at

    normalized["meta"] = meta
    return normalized


def is_record_expired(
    record: Dict[str, Any],
    parse_expires_at_fn: Callable[[Any], Optional[str]],
    now_ts: Optional[float] = None,
) -> bool:
    """Return ``True`` when a record is expired and not on legal hold."""
    value = record.get("value") or {}
    if not isinstance(value, dict):
        return False

    meta = value.get("meta") or {}
    if not isinstance(meta, dict):
        return False

    if bool(meta.get("legal_hold", False)):
        return False

    expires_at = parse_expires_at_fn(meta.get("expires_at"))
    if not expires_at:
        return False

    try:
        expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False

    now = now_ts if now_ts is not None else time.time()
    return expire_dt.timestamp() <= float(now)


def is_record_legal_hold(record: Dict[str, Any]) -> bool:
    """Return ``True`` when record has legal-hold metadata."""
    value = record.get("value") or {}
    if not isinstance(value, dict):
        return False
    meta = value.get("meta") or {}
    if not isinstance(meta, dict):
        return False
    return bool(meta.get("legal_hold", False))


def should_cascade_delete_semantic(
    record: Dict[str, Any],
    user_id: str,
    erased_keys: Set[str],
) -> bool:
    """Return ``True`` when semantic lineage indicates cascade deletion."""
    if not erased_keys:
        return False

    value = record.get("value") or {}
    if not isinstance(value, dict):
        return False

    if str(value.get("kind") or "") != "semantic":
        return False

    meta = value.get("meta") or {}
    if not isinstance(meta, dict):
        return False

    if str(meta.get("user_id") or "") != user_id:
        return False

    if bool(meta.get("legal_hold", False)):
        return False

    source_keys = meta.get("source_episode_keys") or []
    if not isinstance(source_keys, list):
        return False

    return any(str(key) in erased_keys for key in source_keys)
