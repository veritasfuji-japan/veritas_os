# veritas_os/core/pipeline_persistence.py
# -*- coding: utf-8 -*-
"""
Pipeline persistence helpers – path resolution, decision loading, dataset/trustlog fallback.

Extracted from pipeline.py to reduce module size.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# =========================================================
# repo root & constants
# =========================================================

# ★ セキュリティ: __file__ を resolve() 済みなので REPO_ROOT はシンボリックリンク解決済み。
# _enforce_path_policy() での relative_to() チェックが安全に機能する。
REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os

# Unicode categories unsafe for use in ID strings (control, format, separators)
_UNSAFE_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})

# Replay compat
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


# =========================================================
# _to_bool (minimal local copy to avoid circular imports)
# =========================================================

def _to_bool(v: Any) -> bool:
    """Convert value to bool (for env vars, config values, etc.)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


# =========================================================
# Safe logging paths (do not crash import)
# =========================================================

def _safe_paths(
    *,
    _warn: Optional[Callable[..., None]] = None,
) -> Tuple[Path, Path, Path, Path]:
    """
    Return (LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG) safely.
    Prefer veritas_os.logging.paths if available; else fallback to repo-local dirs.
    Also allow env overrides:
      - VERITAS_LOG_DIR
      - VERITAS_DATASET_DIR
    """
    env_log = (os.getenv("VERITAS_LOG_DIR") or "").strip()
    env_ds = (os.getenv("VERITAS_DATASET_DIR") or "").strip()

    allow_external = _to_bool(os.getenv("VERITAS_ALLOW_EXTERNAL_PATHS", "0"))
    if allow_external:
        logger.warning(
            "[SECURITY][pipeline] VERITAS_ALLOW_EXTERNAL_PATHS=1 is enabled; "
            "external log/dataset paths are permitted."
        )

    def _enforce_path_policy(candidate: Path, *, source_name: str) -> Optional[Path]:
        """Validate a candidate path against the pipeline write policy.

        Security policy:
        - By default, only paths under ``REPO_ROOT`` are accepted.
        - External paths can be explicitly allowed by setting
          ``VERITAS_ALLOW_EXTERNAL_PATHS=1``.
        """
        resolved = candidate.resolve()
        if allow_external:
            return resolved

        try:
            resolved.relative_to(REPO_ROOT)
            return resolved
        except ValueError:
            masked_candidate = f"<redacted_path:{candidate.name or 'path'}>"
            logger.warning(
                "[SECURITY][pipeline] Ignoring %s=%r outside REPO_ROOT (%s). "
                "Set VERITAS_ALLOW_EXTERNAL_PATHS=1 to allow explicitly.",
                source_name,
                masked_candidate,
                REPO_ROOT,
            )
            return None

    def _resolve_within_repo(path_text: str, *, env_name: str) -> Optional[Path]:
        """Resolve and validate environment override directory.

        Security policy:
        - By default, only paths under ``REPO_ROOT`` are accepted.
        - External paths can be explicitly allowed by setting
          ``VERITAS_ALLOW_EXTERNAL_PATHS=1``.
        """
        if not path_text:
            return None

        return _enforce_path_policy(Path(path_text), source_name=env_name)

    _warn_fn = _warn or (lambda msg: logger.warning(msg))

    try:
        from veritas_os.logging import paths as lp

        env_log_path = _resolve_within_repo(env_log, env_name="VERITAS_LOG_DIR")
        env_ds_path = _resolve_within_repo(env_ds, env_name="VERITAS_DATASET_DIR")

        default_log_dir = _enforce_path_policy(
            Path(getattr(lp, "LOG_DIR")),
            source_name="logging.paths.LOG_DIR",
        )
        default_dataset_dir = _enforce_path_policy(
            Path(getattr(lp, "DATASET_DIR")),
            source_name="logging.paths.DATASET_DIR",
        )
        LOG_DIR = env_log_path or default_log_dir or (REPO_ROOT / "logs").resolve()
        DATASET_DIR = (
            env_ds_path
            or default_dataset_dir
            or (REPO_ROOT / "dataset").resolve()
        )
        default_val_json = _enforce_path_policy(
            Path(getattr(lp, "VAL_JSON")),
            source_name="logging.paths.VAL_JSON",
        )
        default_meta_log = _enforce_path_policy(
            Path(getattr(lp, "META_LOG")),
            source_name="logging.paths.META_LOG",
        )
        VAL_JSON = default_val_json or (LOG_DIR / "value_ema.json").resolve()
        META_LOG = default_meta_log or (LOG_DIR / "meta.log").resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG
    except (ImportError, AttributeError, OSError) as e:
        _warn_fn(f"[WARN][pipeline] logging.paths import failed -> fallback: {repr(e)}")
        env_log_path = _resolve_within_repo(env_log, env_name="VERITAS_LOG_DIR")
        env_ds_path = _resolve_within_repo(env_ds, env_name="VERITAS_DATASET_DIR")
        LOG_DIR = env_log_path or (REPO_ROOT / "logs").resolve()
        DATASET_DIR = env_ds_path or (REPO_ROOT / "dataset").resolve()
        VAL_JSON = (LOG_DIR / "value_ema.json").resolve()
        META_LOG = (LOG_DIR / "meta.log").resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG


# =========================================================
# Dataset writer fallbacks
# =========================================================

def _fallback_build_dataset_record(
    *, req_payload: dict, res_payload: dict, meta: dict, eval_meta: dict,
) -> dict:
    return {"req": req_payload, "res": res_payload, "meta": meta, "eval": eval_meta}


def _fallback_append_dataset_record(_rec: dict) -> None:
    return None


def load_dataset_writer(
    _warn: Optional[Callable[..., None]] = None,
) -> Tuple[Any, Any]:
    """Import dataset_writer or return fallbacks. Returns (build_fn, append_fn)."""
    _warn_fn = _warn or (lambda msg: logger.warning(msg))
    try:
        from veritas_os.logging.dataset_writer import (
            build_dataset_record,
            append_dataset_record,
        )
        return build_dataset_record, append_dataset_record
    except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
        _warn_fn(f"[WARN][pipeline] dataset_writer import failed: {repr(e)}")
        return _fallback_build_dataset_record, _fallback_append_dataset_record


# =========================================================
# Trust log fallbacks
# =========================================================

def _fallback_append_trust_log(_entry: dict) -> None:
    return None


def _fallback_write_shadow_decide(
    request_id: str,
    body: dict,
    chosen: dict,
    telos_score: float,
    fuji: dict,
) -> None:
    return None


def load_trust_log() -> Tuple[Any, Any]:
    """Import trust_log or return fallbacks. Returns (append_fn, shadow_fn)."""
    try:
        from veritas_os.logging.trust_log import (
            append_trust_log,
            write_shadow_decide,
        )
        return append_trust_log, write_shadow_decide
    except (ImportError, ModuleNotFoundError):  # pragma: no cover
        return _fallback_append_trust_log, _fallback_write_shadow_decide


# =========================================================
# EVIDENCE_MAX
# =========================================================

_EVIDENCE_MAX_UPPER = 10000  # Upper bound to prevent unreasonable memory usage


def resolve_evidence_max() -> int:
    """Parse VERITAS_EVIDENCE_MAX env var with validation."""
    try:
        val = int(os.getenv("VERITAS_EVIDENCE_MAX", "50"))
    except (ValueError, TypeError):
        logger.warning(
            "VERITAS_EVIDENCE_MAX=%r is not a valid integer, using default 50",
            os.getenv("VERITAS_EVIDENCE_MAX"),
        )
        return 50
    if not (1 <= val <= _EVIDENCE_MAX_UPPER):
        logger.warning(
            "VERITAS_EVIDENCE_MAX=%d out of bounds [1,%d], using default 50",
            val,
            _EVIDENCE_MAX_UPPER,
        )
        return 50
    return val
