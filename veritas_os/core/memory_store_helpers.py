"""Helper functions for MemoryStore record filtering and KVS search.

These helpers keep MemoryStore I/O in ``memory.py`` while moving pure record
selection and scoring logic into a focused module.
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Callable, Dict, List, Optional


def normalize_document_lifecycle(
    value: Any,
    *,
    default_retention_class: str,
    allowed_retention_classes: set[str],
    parse_expires_at: Callable[[Any], Optional[str]],
) -> Any:
    """Normalize lifecycle metadata for MemoryStore-compatible documents.

    The helper is intentionally side-effect free so ``memory.py`` can reuse it
    from compatibility hooks without growing new branching logic inline.
    """
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

    raw_hold = meta.get("legal_hold", False)
    if isinstance(raw_hold, str):
        legal_hold = raw_hold.strip().lower() in ("true", "1", "yes")
    else:
        legal_hold = bool(raw_hold)

    meta["retention_class"] = retention_class
    meta["legal_hold"] = legal_hold
    meta["expires_at"] = parse_expires_at(meta.get("expires_at"))
    normalized["meta"] = meta
    return normalized


def is_record_expired_compat(
    record: Dict[str, Any],
    *,
    parse_expires_at: Callable[[Any], Optional[str]],
    now_ts: Optional[float] = None,
) -> bool:
    """Return whether a MemoryStore record is expired for compat wrappers."""
    value = record.get("value") or {}
    if not isinstance(value, dict):
        return False

    meta = value.get("meta") or {}
    if not isinstance(meta, dict):
        return False

    raw_hold = meta.get("legal_hold", False)
    if isinstance(raw_hold, str):
        hold = raw_hold.strip().lower() in ("true", "1", "yes")
    else:
        hold = bool(raw_hold)
    if hold:
        return False

    expires_at = parse_expires_at(meta.get("expires_at"))
    if not expires_at:
        return False

    try:
        expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False

    now = now_ts if now_ts is not None else time.time()
    return expire_dt.timestamp() <= float(now)


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


def erase_user_records(
    *,
    store: Any,
    helper_module: Any,
    original_helper: Callable[..., Any],
    fallback_helper: Callable[..., Any],
    user_id: str,
    reason: str,
    actor: str,
) -> Dict[str, Any]:
    """Erase user records while preserving monkeypatch-friendly compat routing."""
    helper = helper_module.erase_user_data
    if helper is original_helper:
        helper = fallback_helper

    data = store._load_all(copy=True, use_cache=False)
    kept_records, report = helper(
        data=data,
        user_id=user_id,
        reason=reason,
        actor=actor,
    )
    saved = store._save_all(kept_records)
    report["ok"] = bool(saved)
    return report


def recent_records_compat(
    *,
    store: Any,
    helper_module: Any,
    original_helper: Callable[..., Any],
    fallback_helper: Callable[..., Any],
    user_id: str,
    limit: int = 20,
    contains: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent records via the active compat helper implementation."""
    helper = helper_module.filter_recent_records
    if helper is original_helper:
        helper = fallback_helper
    return helper(
        store.list_all(user_id),
        contains=contains,
        limit=limit,
    )


def search_records_compat(
    *,
    store: Any,
    helper_module: Any,
    original_helper: Callable[..., Any],
    fallback_helper: Callable[..., Any],
    query: str,
    k: int = 10,
    kinds: Optional[List[str]] = None,
    min_sim: float = 0.0,
    user_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Run fallback KVS search while keeping compat monkeypatch points intact."""
    helper = helper_module.build_kvs_search_hits
    if helper is original_helper:
        helper = fallback_helper
    episodic = helper(
        store._load_all(copy=True),
        query=query,
        k=k,
        kinds=kinds,
        min_sim=min_sim,
        user_id=user_id,
    )
    if not episodic:
        return {}
    return {"episodic": episodic}


def put_episode_record(
    *,
    store: Any,
    text: str,
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    mem_vec: Any = None,
    logger: Any = None,
    time_module: Any = time,
    **kwargs: Any,
) -> str:
    """Persist an episodic record while keeping optional vector fallback safe."""
    record: Dict[str, Any] = {
        "text": text,
        "tags": tags or [],
        "meta": meta or {},
    }
    for key, value in kwargs.items():
        if key not in record:
            record[key] = value

    user_id = (record.get("meta") or {}).get("user_id", "episodic")
    key = f"episode_{int(time_module.time())}"
    store.put(user_id, key, record)

    if mem_vec is not None:
        try:
            mem_vec.add(
                kind="episodic",
                text=text,
                tags=tags or [],
                meta=meta or {},
            )
        except Exception as exc:
            if logger is not None:
                logger.warning(
                    "[MemoryOS] put_episode MEM_VEC.add error: %s",
                    exc,
                )

    return key


def summarize_records_for_planner(
    *,
    store: Any,
    user_id: str,
    query: str,
    limit: int,
    build_summary: Callable[[List[Dict[str, Any]]], str],
) -> str:
    """Build planner-facing text from MemoryStore search results."""
    result = store.search(query=query, k=limit, user_id=user_id)
    episodic = result.get("episodic") or []
    return build_summary(episodic)
