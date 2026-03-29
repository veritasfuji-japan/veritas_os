# veritas_os/core/pipeline_gate.py
# -*- coding: utf-8 -*-
"""
Pipeline gate helpers – gate prediction, value stats I/O, alternative deduplication.

Extracted from pipeline.py to reduce module size.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =========================================================
# MemoryModel gate prediction
# =========================================================

MEM_VEC: Any = None
MEM_CLF: Any = None


def _default_predict_gate_label(_text: str) -> Dict[str, float]:
    return {"allow": 0.5}


# Module-level predict_gate_label – overwritten below if model is available
predict_gate_label = _default_predict_gate_label


def _mem_model_path() -> str:
    try:
        from veritas_os.core.models import memory_model as mm
        for k in ("MODEL_FILE", "MODEL_PATH"):
            if hasattr(mm, k):
                return str(getattr(mm, k))
    except Exception:  # subsystem resilience: intentionally broad
        logger.debug("_mem_model_path: import/attr lookup failed", exc_info=True)
    return ""


def _load_memory_model() -> Tuple[Any, Any, Any]:
    """Import memory model and return (MEM_VEC, MEM_CLF, predict_gate_label).

    Returns the default predict_gate_label if the model is unavailable.
    """
    _mem_vec: Any = None
    _mem_clf: Any = None
    _pgl_fn = _default_predict_gate_label

    try:
        from veritas_os.core.models import memory_model as memory_model_core

        _mem_vec = getattr(memory_model_core, "MEM_VEC", None)
        _mem_clf = getattr(memory_model_core, "MEM_CLF", None)

        if hasattr(memory_model_core, "predict_gate_label"):
            from veritas_os.core.models.memory_model import (
                predict_gate_label as _pgl_raw,
            )

            def _safe_pgl(text: str) -> Dict[str, float]:
                try:
                    d = _pgl_raw(text)
                    return d if isinstance(d, dict) else {"allow": 0.5}
                except Exception:  # subsystem resilience: intentionally broad
                    logger.debug("predict_gate_label failed", exc_info=True)
                    return {"allow": 0.5}

            _pgl_fn = _safe_pgl

    except Exception:  # subsystem resilience: intentionally broad
        logger.debug("memory_model import failed", exc_info=True)

    return _mem_vec, _mem_clf, _pgl_fn


# Eagerly load at import time (mirrors original pipeline.py behavior)
MEM_VEC, MEM_CLF, predict_gate_label = _load_memory_model()


def _allow_prob(text: str) -> float:
    d = predict_gate_label(text)
    try:
        return float(d.get("allow", 0.0))
    except (ValueError, TypeError, AttributeError):
        return 0.0


# =========================================================
# Value stats I/O (EMA persistence)
# =========================================================

def _load_valstats(val_json_path: Path) -> Dict[str, Any]:
    try:
        p = Path(val_json_path)
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}


def _save_valstats(
    d: Dict[str, Any],
    val_json_path: Path,
    *,
    _HAS_ATOMIC_IO: bool = False,
    _atomic_write_json: Any = None,
) -> None:
    try:
        p = Path(val_json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_ATOMIC_IO and _atomic_write_json is not None:
            _atomic_write_json(p, d, indent=2)
        else:
            # Atomic write via temp-file + rename to prevent data
            # corruption if the process crashes mid-write.
            fd, tmp_path = tempfile.mkstemp(
                dir=str(p.parent), suffix=".tmp", prefix=".valstats_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                os.replace(tmp_path, str(p))
            except BaseException:
                # Clean up the temp file on any failure.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    except OSError as e:
        logger.warning("_save_valstats failed: %s", e)


# =========================================================
# Alternative deduplication
# =========================================================

def _dedupe_alts_fallback(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for a in alts or []:
        if not isinstance(a, dict):
            continue
        key = (str(a.get("title") or "").strip(), str(a.get("description") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _dedupe_alts(
    alts: List[Dict[str, Any]],
    veritas_core: Any = None,
) -> List[Dict[str, Any]]:
    """Deduplicate alternatives, preferring kernel helper if present."""
    try:
        if veritas_core is not None and hasattr(veritas_core, "_dedupe_alts"):
            result = veritas_core._dedupe_alts(alts)
            if isinstance(result, list):
                return result
            logger.debug(
                "_dedupe_alts: kernel helper returned %s, expected list",
                type(result).__name__,
            )
    except Exception:  # subsystem resilience: kernel._dedupe_alts may raise arbitrary errors
        logger.debug(
            "_dedupe_alts: kernel helper failed, using fallback", exc_info=True
        )
    return _dedupe_alts_fallback(alts)
