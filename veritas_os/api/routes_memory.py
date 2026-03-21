# veritas_os/api/routes_memory.py
"""Memory CRUD API endpoints."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Header

from veritas_os.api.schemas import (
    MemoryEraseRequest,
    MemoryGetRequest,
    MemoryPutRequest,
    MemorySearchRequest,
)
from veritas_os.api.constants import VALID_MEMORY_KINDS

logger = logging.getLogger(__name__)

router = APIRouter()


# Route handlers intentionally catch only expected operational failures so
# process-level BaseException signals (for example KeyboardInterrupt/SystemExit)
# still propagate. The public response contract stays unchanged.
MEMORY_ROUTE_EXCEPTIONS = (
    AttributeError,
    ConnectionError,
    JSONDecodeError,
    KeyError,
    OSError,
    PermissionError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


def _classify_memory_failure(exc: Exception) -> str:
    """Classify MemoryOS failures without changing the public response contract.

    The returned code is additive metadata for operators and clients that need
    finer auditability. Existing ``ok`` / ``status`` / ``errors[]`` fields remain
    unchanged so callers can adopt the new codes incrementally.
    """
    if isinstance(exc, PermissionError):
        return "security_policy_rejection"
    if isinstance(exc, (ValueError, TypeError)):
        return "validation_failure"
    if isinstance(exc, (JSONDecodeError, OSError)):
        return "serialization_storage_failure"
    if isinstance(exc, (ConnectionError, TimeoutError, RuntimeError)):
        return "backend_unavailable"
    return "unknown_failure"


def _build_memory_stage_error(stage: str, exc: Exception) -> Dict[str, str]:
    """Return a sanitized stage error payload for partial MemoryOS failures."""
    logger.warning("[MemoryOS][%s] Error: %s", stage, exc)
    return {
        "stage": stage,
        "message": f"{stage} save failed",
        "error_code": _classify_memory_failure(exc),
    }


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


# ------------------------------------------------------------------
# Memory store adapter helpers
# ------------------------------------------------------------------

def _store_put(store: Any, user_id: str, key: str, value: dict) -> None:
    if not hasattr(store, "put"):
        raise RuntimeError("store.put not found")
    fn = store.put
    try:
        fn(user_id, key=key, value=value)
        return
    except TypeError:
        pass
    try:
        fn(user_id, key, value)
        return
    except TypeError:
        fn(key, value)  # type: ignore


def _store_get(store: Any, user_id: str, key: str) -> Any:
    if not hasattr(store, "get"):
        raise RuntimeError("store.get not found")
    fn = store.get
    try:
        return fn(user_id, key=key)
    except TypeError:
        try:
            return fn(user_id, key)
        except TypeError:
            return fn(key)  # type: ignore


def _store_search(store: Any, *, query: str, k: int, kinds: Any, min_sim: float, user_id: Optional[str]) -> Any:
    if not hasattr(store, "search"):
        raise RuntimeError("store.search not found")
    fn = store.search
    try:
        return fn(query=query, k=k, kinds=kinds, min_sim=min_sim, user_id=user_id)
    except TypeError:
        pass
    try:
        return fn(query=query, k=k, kinds=kinds, min_sim=min_sim)
    except TypeError:
        pass
    try:
        return fn(query=query, k=k)
    except TypeError:
        return fn(query)


def _validate_memory_kinds(kinds: Any) -> Tuple[Optional[list[str]], Optional[str]]:
    """Validate and normalize memory search kinds against allow-list."""
    if kinds is None:
        return None, None

    raw_kinds: list[Any]
    if isinstance(kinds, str):
        raw_kinds = [kinds]
    elif isinstance(kinds, list):
        raw_kinds = kinds
    else:
        return None, "kinds must be a string or list of strings"

    normalized_kinds: list[str] = []
    invalid_kinds: list[str] = []

    for raw_kind in raw_kinds:
        if not isinstance(raw_kind, str):
            return None, "kinds must be a string or list of strings"
        normalized_kind = raw_kind.strip().lower()
        if normalized_kind not in VALID_MEMORY_KINDS:
            invalid_kinds.append(normalized_kind)
            continue
        if normalized_kind not in normalized_kinds:
            normalized_kinds.append(normalized_kind)

    if invalid_kinds:
        return None, f"invalid kinds: {invalid_kinds}"

    return normalized_kinds, None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/v1/memory/put")
def memory_put(body: MemoryPutRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> Dict[str, Any]:
    """Store memory data and surface stage-level partial failures explicitly."""
    srv = _get_server()
    store = srv.get_memory_store()
    if store is None:
        logger.warning("memory_put: memory store unavailable: %s", srv._memory_store_state.err)
        return {
            "ok": False,
            "error": "memory store unavailable",
            "error_code": "backend_unavailable",
        }

    try:
        user_id = srv._resolve_memory_user_id(body.user_id, x_api_key)
    except MEMORY_ROUTE_EXCEPTIONS as exc:
        logger.error("[MemoryOS][resolve_user] Error: %s", exc)
        return {
            "ok": False,
            "error": "memory operation failed",
            "error_code": _classify_memory_failure(exc),
        }

    key = body.key or f"memory_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    value = body.value or {}

    text = body.text.strip()
    tags = body.tags
    meta = body.meta or {}

    retention_class = str(
        body.retention_class or meta.get("retention_class") or "standard"
    ).strip().lower()
    expires_at = body.expires_at if body.expires_at is not None else meta.get("expires_at")
    legal_hold = body.legal_hold or bool(meta.get("legal_hold", False))

    errors: list[Dict[str, str]] = []
    legacy_saved = False
    if value:
        try:
            _store_put(store, user_id, key, value)
            legacy_saved = True
        except MEMORY_ROUTE_EXCEPTIONS as exc:
            errors.append(_build_memory_stage_error("legacy", exc))

    kind = body.kind
    if kind not in VALID_MEMORY_KINDS:
        kind = "semantic"

    new_id = None
    if text:
        try:
            text_clean = srv.redact(text)
            meta_for_store = dict(meta)
            meta_for_store.setdefault("user_id", user_id)
            meta_for_store.setdefault("kind", kind)
            meta_for_store["retention_class"] = retention_class
            meta_for_store["expires_at"] = expires_at
            meta_for_store["legal_hold"] = legal_hold

            if hasattr(store, "put"):
                vector_item = {
                    "text": text_clean,
                    "tags": tags,
                    "meta": meta_for_store,
                }
                try:
                    new_id = store.put(kind, vector_item)
                except TypeError:
                    if hasattr(store, "put_episode"):
                        new_id = store.put_episode(
                            text=text_clean,
                            tags=tags,
                            meta=meta_for_store,
                        )
                    else:
                        raise
            elif hasattr(store, "put_episode"):
                new_id = store.put_episode(
                    text=text_clean,
                    tags=tags,
                    meta=meta_for_store,
                )
            else:
                episode_key = f"episode_{int(time.time())}"
                _store_put(
                    store,
                    user_id,
                    episode_key,
                    {"text": text_clean, "tags": tags, "meta": meta_for_store},
                )
                new_id = episode_key
        except MEMORY_ROUTE_EXCEPTIONS as exc:
            errors.append(_build_memory_stage_error("vector", exc))

    ok = legacy_saved or bool(new_id) or (not value and not text)
    response: Dict[str, Any] = {
        "ok": ok,
        "status": "ok" if ok and not errors else "partial_failure" if ok else "failed",
        "legacy": {"saved": legacy_saved, "key": key if legacy_saved else None},
        "vector": {
            "saved": bool(new_id),
            "id": new_id,
            "kind": kind if new_id else None,
            "tags": tags if new_id else None,
        },
        "size": len(str(value)) if value else len(text),
        "lifecycle": {
            "retention_class": retention_class,
            "expires_at": expires_at,
            "legal_hold": legal_hold,
        },
    }
    if errors:
        response["errors"] = errors
        if not ok:
            response["error"] = "memory operation failed"
            response["error_code"] = (
                errors[0].get("error_code") if len(errors) == 1 else "partial_failure"
            )
    return response


@router.post("/v1/memory/search")
def memory_search(payload: MemorySearchRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> Dict[str, Any]:
    srv = _get_server()
    store = srv.get_memory_store()
    if store is None:
        logger.warning("memory_search: memory store unavailable: %s", srv._memory_store_state.err)
        return {
            "ok": False,
            "error": "memory store unavailable",
            "error_code": "backend_unavailable",
            "hits": [],
            "count": 0,
        }

    try:
        q = payload.query
        kinds = payload.kinds
        k = payload.k
        min_sim = payload.min_sim
        user_id = srv._resolve_memory_user_id(payload.user_id, x_api_key)

        validated_kinds, kinds_error = _validate_memory_kinds(kinds)
        if kinds_error:
            return {
                "ok": False,
                "error": kinds_error,
                "error_code": "validation_failure",
                "hits": [],
                "count": 0,
            }

        raw_hits = _store_search(
            store,
            query=q,
            k=k,
            kinds=validated_kinds,
            min_sim=min_sim,
            user_id=user_id,
        )

        if isinstance(raw_hits, dict):
            flat_hits: list = []
            for kind_hits in raw_hits.values():
                if isinstance(kind_hits, list):
                    flat_hits.extend(kind_hits)
            raw_hits = flat_hits
        elif not isinstance(raw_hits, list):
            raw_hits = list(raw_hits) if raw_hits else []

        norm_hits = []
        for h in (raw_hits or []):
            if isinstance(h, dict):
                meta = h.get("meta") or {}
                if meta.get("user_id") == user_id:
                    norm_hits.append(h)
                continue

        return {"ok": True, "hits": norm_hits, "count": len(norm_hits)}

    except MEMORY_ROUTE_EXCEPTIONS as e:
        logger.error("[MemoryOS][search] Error: %s", e)
        return {
            "ok": False,
            "error": "memory search failed",
            "error_code": _classify_memory_failure(e),
            "hits": [],
            "count": 0,
        }


@router.post("/v1/memory/get")
def memory_get(body: MemoryGetRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> Dict[str, Any]:
    srv = _get_server()
    store = srv.get_memory_store()
    if store is None:
        return {
            "ok": False,
            "error": "memory store unavailable",
            "error_code": "backend_unavailable",
            "value": None,
        }

    try:
        uid = srv._resolve_memory_user_id(body.user_id, x_api_key)
        key = body.key
        value = _store_get(store, uid, key)
        return {"ok": True, "value": value}
    except MEMORY_ROUTE_EXCEPTIONS as e:
        logger.error("memory_get failed: %s", e)
        return {
            "ok": False,
            "error": "memory retrieval failed",
            "error_code": _classify_memory_failure(e),
            "value": None,
        }


@router.post("/v1/memory/erase")
def memory_erase(body: MemoryEraseRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> Dict[str, Any]:
    """Erase a tenant's memories with legal-hold protection and audit log."""
    srv = _get_server()
    store = srv.get_memory_store()
    if store is None:
        return {
            "ok": False,
            "error": "memory store unavailable",
            "error_code": "backend_unavailable",
        }

    try:
        user_id = srv._resolve_memory_user_id(body.user_id, x_api_key)
        reason = body.reason.strip()
        actor = body.actor.strip()

        if hasattr(store, "erase_user"):
            report = store.erase_user(user_id=user_id, reason=reason, actor=actor)
            report.setdefault("ok", True)
            return report

        return {
            "ok": False,
            "error": "erase operation unsupported by active memory backend",
            "error_code": "backend_unavailable",
        }
    except MEMORY_ROUTE_EXCEPTIONS as e:
        logger.error("memory_erase failed: %s", e)
        return {
            "ok": False,
            "error": "memory erase failed",
            "error_code": _classify_memory_failure(e),
        }
