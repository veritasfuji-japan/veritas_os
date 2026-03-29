"""Pure helper functions for MemoryOS search result shaping.

These helpers keep side-effect-free result normalization out of ``memory.py``
so the main module can focus on storage orchestration and vector/KVS access.
The module stays within the MemoryOS boundary and does not change Planner,
Kernel, FUJI, or external storage responsibilities.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def dedup_hits(hits: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Deduplicate hits by ``(text, user_id)`` while preserving order."""
    unique: List[Dict[str, Any]] = []
    seen = set()

    for hit in hits:
        if not isinstance(hit, dict):
            continue

        text = str(hit.get("text") or "")
        meta = hit.get("meta") or {}
        user_id = str((meta or {}).get("user_id") or "")
        key = (text, user_id)

        if key in seen:
            continue

        seen.add(key)
        unique.append(hit)

        if len(unique) >= k:
            break

    return unique


def collect_candidate_hits(raw: Any) -> List[Dict[str, Any]]:
    """Normalize vector-search payloads into a list of hit dictionaries."""
    if isinstance(raw, list):
        return [hit for hit in raw if isinstance(hit, dict)]

    if isinstance(raw, dict):
        for key in ("hits", "episodic", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [hit for hit in value if isinstance(hit, dict)]

    return []


def filter_hits_for_user(
    hits: List[Dict[str, Any]],
    user_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Keep hits whose ``meta.user_id`` matches the requested user or is unset."""
    if user_id is None:
        return hits

    filtered: List[Dict[str, Any]] = []
    for hit in hits:
        meta = hit.get("meta") or {}
        hit_user_id = meta.get("user_id")
        if hit_user_id is None or hit_user_id == user_id:
            filtered.append(hit)

    return filtered


def normalize_store_hits(raw: Any) -> List[Dict[str, Any]]:
    """Normalize MemoryStore/KVS search responses into a hit list."""
    if isinstance(raw, dict):
        episodic = raw.get("episodic") or []
        if isinstance(episodic, list):
            return [hit for hit in episodic if isinstance(hit, dict)]

    if isinstance(raw, list):
        return [hit for hit in raw if isinstance(hit, dict)]

    return []
