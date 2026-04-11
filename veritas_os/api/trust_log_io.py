"""File-based trust-log I/O primitives (LEGACY COMPAT — jsonl backend only).

These functions provide the low-level file I/O for TrustLog persistence:
aggregate JSON loading, JSONL append, file-permission hardening, and
shadow snapshot writes.

Backend awareness
-----------------
These primitives are the operational persistence path **only** when
``VERITAS_TRUSTLOG_BACKEND=jsonl`` (the default).

When ``backend=postgresql``, TrustLog persistence is handled entirely
by ``app.state.trust_log_store`` (a ``PostgresTrustLogStore`` instance
created by ``storage/factory.py`` and wired in ``lifespan.py``).
The functions here are NOT the persistence source of truth in that case.

The exception is ``write_shadow_decide_snapshot``, which always writes
to local files regardless of backend for replay/audit support.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class TrustLogLoadResult:
    """Structured trust-log aggregate load result used to avoid silent data loss."""

    items: list
    status: str
    error: Optional[str] = None


def load_logs_json_result(
    path: Optional[Path],
    *,
    max_log_file_size: int,
    effective_log_paths: Callable[[], tuple[Path, Path, Path]],
    logger: Any,
) -> TrustLogLoadResult:
    """Load trust-log aggregate JSON and preserve unreadable/degraded state."""
    try:
        if path is None:
            _, log_json, _ = effective_log_paths()
            path = log_json

        if not path.exists():
            return TrustLogLoadResult(items=[], status="missing")

        file_size = path.stat().st_size
        if file_size > max_log_file_size:
            logger.warning("Log file too large (%d bytes), skipping load", file_size)
            return TrustLogLoadResult(
                items=[],
                status="too_large",
                error=f"aggregate log exceeds {max_log_file_size} bytes",
            )

        with open(path, "r", encoding="utf-8") as file_obj:
            obj = json.load(file_obj)

        if isinstance(obj, dict):
            items = obj.get("items", [])
        elif isinstance(obj, list):
            items = obj
        else:
            return TrustLogLoadResult(
                items=[],
                status="invalid",
                error="aggregate log payload must be a list or object",
            )

        if not isinstance(items, list):
            return TrustLogLoadResult(
                items=[],
                status="invalid",
                error="aggregate log payload is not a list",
            )

        return TrustLogLoadResult(items=items, status="ok")
    except Exception as exc:
        logger.debug("_load_logs_json: failed to load %s", path, exc_info=True)
        return TrustLogLoadResult(items=[], status="unreadable", error=str(exc))


def load_logs_json(
    path: Optional[Path],
    *,
    max_log_file_size: int,
    effective_log_paths: Callable[[], tuple[Path, Path, Path]],
    logger: Any,
) -> list:
    """Load trust-log aggregate JSON safely with legacy list-only compatibility."""
    return load_logs_json_result(
        path,
        max_log_file_size=max_log_file_size,
        effective_log_paths=effective_log_paths,
        logger=logger,
    ).items


def secure_chmod(path: Path, *, logger: Any, errstr: Callable[[Exception], str]) -> None:
    """Set restrictive file permissions (0600) for sensitive trust-log artifacts."""
    try:
        os.chmod(path, 0o600)
    except Exception as exc:
        logger.debug("chmod 0o600 failed for %s: %s", path, errstr(exc))


def save_json(
    path: Path,
    items: list,
    *,
    has_atomic_io: bool,
    atomic_write_json: Optional[Callable[..., None]],
    secure_chmod_fn: Callable[[Path], None],
) -> None:
    """Persist trust-log aggregate JSON with optional atomic write backend."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    if has_atomic_io and atomic_write_json is not None:
        atomic_write_json(path, {"items": items}, indent=2)
    else:
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump({"items": items}, file_obj, ensure_ascii=False, indent=2)
    if is_new:
        secure_chmod_fn(path)


def append_trust_log_entry(
    entry: Dict[str, Any],
    *,
    effective_log_paths: Callable[[], tuple[Path, Path, Path]],
    has_atomic_io: bool,
    atomic_append_line: Optional[Callable[..., None]],
    load_logs_json_result_fn: Callable[[Optional[Path]], TrustLogLoadResult],
    load_logs_json_fn: Callable[[Optional[Path]], list],
    save_json_fn: Callable[[Path, list], None],
    secure_chmod_fn: Callable[[Path], None],
    publish_event: Callable[[str, Dict[str, Any]], None],
    logger: Any,
    errstr: Callable[[Exception], str],
    trust_log_lock: Optional[Lock] = None,
) -> None:
    """Append trust-log records to JSONL and aggregate JSON with thread safety."""
    log_dir, log_json, log_jsonl = effective_log_paths()

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("LOG_DIR mkdir failed: %s", errstr(exc))
        return

    lock = trust_log_lock or Lock()
    with lock:
        try:
            jsonl_is_new = not log_jsonl.exists()
            if has_atomic_io and atomic_append_line is not None:
                atomic_append_line(log_jsonl, json.dumps(entry, ensure_ascii=False))
            else:
                with open(log_jsonl, "a", encoding="utf-8") as file_obj:
                    file_obj.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    file_obj.flush()
                    os.fsync(file_obj.fileno())
            if jsonl_is_new:
                secure_chmod_fn(log_jsonl)
        except Exception as exc:
            logger.warning("write trust_log.jsonl failed: %s", errstr(exc))

        load_result = load_logs_json_result_fn(log_json)
        if load_result.status not in {"ok", "missing"}:
            logger.warning(
                "write trust_log.json skipped: aggregate log status=%s error=%s",
                load_result.status,
                load_result.error or "unknown",
            )
            return

        items = list(load_result.items or load_logs_json_fn(log_json))
        items.append(entry)
        try:
            save_json_fn(log_json, items)
            publish_event(
                "trustlog.appended",
                {"request_id": entry.get("request_id"), "kind": entry.get("kind")},
            )
        except Exception as exc:
            logger.warning("write trust_log.json failed: %s", errstr(exc))


def write_shadow_decide_snapshot(
    request_id: str,
    body: Dict[str, Any],
    chosen: Dict[str, Any],
    telos_score: float,
    fuji: Optional[Dict[str, Any]],
    *,
    effective_shadow_dir: Callable[[], Path],
    has_atomic_io: bool,
    atomic_write_json: Optional[Callable[..., None]],
    secure_chmod_fn: Callable[[Path], None],
    logger: Any,
    errstr: Callable[[Exception], str],
) -> None:
    """Persist a shadow snapshot of /decide responses for replay/audit support."""
    shadow_dir = effective_shadow_dir()

    try:
        shadow_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("SHADOW_DIR mkdir failed: %s", errstr(exc))
        return

    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y%m%d_%H%M%S_%f")[:-3]
    output_path = shadow_dir / f"decide_{ts}.json"
    rec = {
        "request_id": request_id,
        "created_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "query": (body.get("query") or (body.get("context") or {}).get("query") or ""),
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": (fuji or {}).get("status"),
    }
    try:
        if has_atomic_io and atomic_write_json is not None:
            atomic_write_json(output_path, rec, indent=2)
        else:
            with open(output_path, "w", encoding="utf-8") as file_obj:
                json.dump(rec, file_obj, ensure_ascii=False, indent=2)
        secure_chmod_fn(output_path)
    except Exception as exc:
        logger.warning("write shadow decide failed: %s", errstr(exc))
