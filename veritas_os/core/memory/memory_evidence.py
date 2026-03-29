"""Memory evidence extraction utilities.

This module isolates evidence conversion/retrieval logic from ``memory.py``
so MemoryStore lifecycle/index responsibilities remain focused.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def hits_to_evidence(
    hits: List[Dict[str, Any]],
    *,
    source_prefix: str = "memory",
) -> List[Dict[str, Any]]:
    """Convert search hits to the Evidence schema used by Kernel/Fuji.

    Invalid records and empty-text records are ignored to keep evidence clean.
    """
    evidence: List[Dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue

        text = str(hit.get("text") or "")
        if not text:
            continue

        evidence.append(
            {
                "source": f"{source_prefix}:{hit.get('id', 'unknown')}",
                "text": text,
                "score": hit.get("score", 0.0),
                "tags": hit.get("tags", []),
                "meta": hit.get("meta", {}),
            }
        )

    return evidence


def get_evidence_for_decision(
    decision: Dict[str, Any],
    *,
    search_fn: Callable[..., Any],
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve evidence records for a decision payload."""
    query = (
        decision.get("query")
        or (decision.get("chosen") or {}).get("query")
        or (decision.get("chosen") or {}).get("title")
        or (decision.get("chosen") or {}).get("description")
        or ""
    )
    query = str(query).strip()
    if not query:
        return []

    context = decision.get("context") or {}
    uid = (
        user_id
        or context.get("user_id")
        or context.get("user")
        or context.get("session_id")
        or None
    )

    hits = search_fn(
        query=query,
        k=top_k,
        user_id=uid,
    )
    if not hits or not isinstance(hits, list):
        return []

    return hits_to_evidence(hits, source_prefix="memory")


def get_evidence_for_query(
    query: str,
    *,
    search_fn: Callable[..., Any],
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve evidence records for a free-text query."""
    normalized_query = (query or "").strip()
    if not normalized_query:
        return []

    hits = search_fn(query=normalized_query, k=top_k, user_id=user_id)
    if not hits or not isinstance(hits, list):
        return []

    return hits_to_evidence(hits, source_prefix="memory")

