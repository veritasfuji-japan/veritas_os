# veritas_os/core/memory_compliance.py
"""
GDPR / user-erasure compliance helpers for MemoryOS.

Provides:
- erase_user_data(): Erase user records with legal-hold awareness and audit trail
- is_record_legal_hold(): Check if a record is under legal hold
- should_cascade_delete_semantic(): Determine cascade deletion for semantic records
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import time
import logging

from .memory_lifecycle import parse_legal_hold

logger = logging.getLogger(__name__)


def is_record_legal_hold(record: Dict[str, Any]) -> bool:
    """Return True when record carries legal hold metadata."""
    value = record.get("value") or {}
    if not isinstance(value, dict):
        return False
    meta = value.get("meta") or {}
    if not isinstance(meta, dict):
        return False
    return parse_legal_hold(meta.get("legal_hold", False))


def should_cascade_delete_semantic(
    record: Dict[str, Any],
    user_id: str,
    erased_keys: set,
) -> bool:
    """Check semantic distill lineage and decide cascade deletion."""
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

    if parse_legal_hold(meta.get("legal_hold", False)):
        return False

    source_keys = meta.get("source_episode_keys") or []
    if not isinstance(source_keys, list):
        return False

    return any(str(key) in erased_keys for key in source_keys)


def erase_user_data(
    data: List[Dict[str, Any]],
    user_id: str,
    reason: str,
    actor: str,
) -> tuple:
    """Erase user records while honoring legal hold, with audit trail.

    Also cascades deletion to semantic memories distilled from erased
    episodic records via ``meta.source_episode_keys`` linkage.

    Args:
        data: Full list of memory records (will not be mutated).
        user_id: The user whose data should be erased.
        reason: Reason for the erasure (for audit).
        actor: Who initiated the erasure (for audit).

    Returns:
        Tuple of (kept_records, report_dict).
    """
    to_delete_keys: set = set()
    legal_hold_count = 0

    for record in data:
        if record.get("user_id") != user_id:
            continue
        if is_record_legal_hold(record):
            legal_hold_count += 1
            continue
        value = record.get("value") or {}
        if isinstance(value, dict):
            source_keys = (value.get("meta") or {}).get("source_episode_keys")
            if isinstance(source_keys, list) and source_keys:
                # semantic lineage records are deleted in cascade phase.
                continue
        to_delete_keys.add(str(record.get("key") or ""))

    cascade_deleted = 0
    kept_records: List[Dict[str, Any]] = []
    deleted_records = 0

    for record in data:
        record_user = record.get("user_id")
        record_key = str(record.get("key") or "")

        if record_user == user_id and record_key in to_delete_keys:
            deleted_records += 1
            continue

        if should_cascade_delete_semantic(record, user_id, to_delete_keys):
            cascade_deleted += 1
            continue

        kept_records.append(record)

    report = {
        "target_user_id": user_id,
        "deleted_count": deleted_records,
        "cascade_deleted_count": cascade_deleted,
        "protected_by_legal_hold": legal_hold_count,
        "reason": reason,
        "actor": actor,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    audit_record = {
        "user_id": "__audit__",
        "key": f"erase_{user_id}_{int(time.time())}",
        "value": {
            "kind": "audit",
            "text": "memory erase executed",
            "meta": {
                "event": "memory_erase",
                "payload": report,
                "retention_class": "regulated",
                "legal_hold": True,
                "expires_at": None,
            },
        },
        "ts": time.time(),
    }
    kept_records.append(audit_record)

    return kept_records, report
