"""Helper functions for MemoryStore record filtering and KVS search.

These helpers keep MemoryStore I/O in ``memory.py`` while moving pure record
selection and scoring logic into a focused module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def extract_record_text(record: Dict[str, Any]) -> str:
    """Return searchable text from a MemoryStore record."""
    value = record.get("value")
    if isinstance(value, dict):
        return str(value.get("query") or value.get("text") or "")
    return str(value or "")


def filter_recent_records(
    items: List[Dict[str, Any]],
    *,
    contains: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Sort records by recency and apply the optional substring filter."""
    ordered = sorted(items, key=lambda record: record.get("ts", 0), reverse=True)
    if not contains:
        return ordered[:limit]

    needle = contains.strip()
    filtered = [
        record for record in ordered if needle in extract_record_text(record)
    ]
    return filtered[:limit]


def simple_score(query: str, text: str) -> float:
    """Compute the lightweight fallback similarity score used by MemoryStore."""
    normalized_query = (query or "").strip().lower()
    normalized_text = (text or "").strip().lower()
    if not normalized_query or not normalized_text:
        return 0.0

    base = 0.5 if (
        normalized_query in normalized_text
        or normalized_text in normalized_query
    ) else 0.0

    query_tokens = set(normalized_query.split())
    text_tokens = set(normalized_text.split())
    if not query_tokens or not text_tokens:
        token_score = 0.0
    else:
        token_score = len(query_tokens & text_tokens) / max(len(query_tokens), 1)

    return min(1.0, base + 0.5 * token_score)


def build_kvs_search_hits(
    records: List[Dict[str, Any]],
    *,
    query: str,
    k: int,
    kinds: Optional[List[str]] = None,
    min_sim: float = 0.0,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build normalized fallback KVS search hits from raw store records."""
    normalized_query = (query or "").strip()
    if not normalized_query:
        return []

    hits: List[Dict[str, Any]] = []
    for record in records:
        if user_id and record.get("user_id") != user_id:
            continue

        value = record.get("value") or {}
        if not isinstance(value, dict):
            continue

        text = str(value.get("text") or value.get("query") or "").strip()
        if not text:
            continue

        score = simple_score(normalized_query, text)
        if score < min_sim:
            continue

        kind = value.get("kind", "episodic")
        if kinds and kind not in kinds:
            continue

        hits.append(
            {
                "id": record.get("key"),
                "text": text,
                "score": float(score),
                "tags": value.get("tags") or [],
                "ts": record.get("ts"),
                "meta": {
                    "user_id": record.get("user_id"),
                    "created_at": record.get("ts"),
                    "kind": kind,
                },
            }
        )

    hits.sort(key=lambda hit: hit.get("score", 0.0), reverse=True)
    return hits[:k]
