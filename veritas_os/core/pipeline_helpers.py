# veritas_os/core/pipeline_helpers.py
# -*- coding: utf-8 -*-
"""
VERITAS Pipeline — pure utility functions & constants.

Extracted from pipeline.py to reduce file size.
All functions here are stateless / pure (no closures, no module-level side-effects).
"""
from __future__ import annotations

import inspect
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .utils import _safe_float, _clip01 as _clip01_base

logger = logging.getLogger(__name__)

# =========================================================
# Pipeline constants (magic numbers consolidated)
# =========================================================
MIN_MEMORY_SIMILARITY = 0.30       # メモリ検索の最小類似度
DEFAULT_CONFIDENCE = 0.55          # デフォルト信頼度（web_search fallback等）
DOC_MIN_CONFIDENCE = 0.75          # ドキュメント証拠の最小信頼度
TELOS_THRESHOLD_MIN = 0.35         # テロス閾値の下限
TELOS_THRESHOLD_MAX = 0.75         # テロス閾値の上限
HIGH_RISK_THRESHOLD = 0.90         # 高リスク判定閾値
BASE_TELOS_THRESHOLD = 0.55        # 基本テロススコア閾値

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os


# =========================================================
# Tiny helpers (no free vars / safe)
# =========================================================

def _to_bool(v: Any) -> bool:
    """Convert value to bool (handles strings, ints, None, env vars, etc.)"""
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    try:
        s = str(v).strip().lower()
    except Exception:
        return False
    if s in ("0", "false", "no", "n", "off", ""):
        return False
    return s in ("1", "true", "yes", "y", "on")


def _warn(msg: str) -> None:
    """警告メッセージを出力（環境変数で抑制可能）"""
    if _to_bool(os.getenv("VERITAS_PIPELINE_WARN", "1")):
        logger.warning(msg)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_str(x: Any, *, limit: int = 2000) -> str:
    try:
        s = "" if x is None else str(x)
    except Exception:
        s = repr(x)
    if limit and len(s) > int(limit):
        return s[: int(limit)]
    return s


def _norm_severity(x: Any) -> str:
    try:
        s = str(x).lower().strip()
    except Exception:
        s = "med"
    if s in ("high", "h", "critical", "crit"):
        return "high"
    if s in ("low", "l"):
        return "low"
    return "med"


def _to_float_or(v: Any, default: float) -> float:
    """_safe_float のエイリアス（後方互換性のため維持）"""
    return _safe_float(v, default)


def _to_dict(o: Any) -> Dict[str, Any]:
    if isinstance(o, dict):
        return o
    if hasattr(o, "model_dump"):
        return o.model_dump(exclude_none=True)  # type: ignore
    if hasattr(o, "dict"):
        return o.dict()  # type: ignore
    if hasattr(o, "__dict__"):
        try:
            return dict(o.__dict__)
        except Exception:
            return {}
    return {}


def _get_request_params(request: Any) -> Dict[str, Any]:
    """
    DummyRequest 互換:
    - request.query_params (starlette)
    - request.params (tests)
    の両方を吸って dict 化する
    """
    out: Dict[str, Any] = {}
    try:
        qp = getattr(request, "query_params", None)
        if qp is not None:
            out.update(dict(qp))
    except Exception:
        pass
    try:
        pm = getattr(request, "params", None)
        if pm is not None:
            out.update(dict(pm))
    except Exception:
        pass
    return out


def _ensure_metrics_contract(extras: Dict[str, Any]) -> None:
    extras.setdefault("metrics", {})
    m = extras["metrics"]
    m.setdefault("mem_hits", 0)
    m.setdefault("memory_evidence_count", 0)
    m.setdefault("web_hits", 0)
    m.setdefault("web_evidence_count", 0)
    m.setdefault("fast_mode", False)
    extras.setdefault("fast_mode", False)


def _norm_alt(o: Any) -> Dict[str, Any]:
    d = _to_dict(o) or {}

    # text/title/description の整形
    text = d.get("text")
    if isinstance(text, str):
        text = text.strip()

    title = d.get("title")
    if not title and text:
        title = text
    d["title"] = str(title or "")

    desc = d.get("description")
    if not desc and text:
        desc = text
    d["description"] = str(desc or "")

    # score 系
    d["score"] = _to_float_or(d.get("score", 1.0), 1.0)
    d["score_raw"] = _to_float_or(d.get("score_raw", d["score"]), d["score"])

    # ★ id は「あるなら保持」、None/空/空白だけ新規発行
    _id = d.get("id")
    if _id is None or (isinstance(_id, str) and _id.strip() == ""):
        d["id"] = uuid4().hex
    else:
        d["id"] = str(_id)

    return d


def _clip01(x: float) -> float:
    """_clip01_base のラッパー（後方互換性のため維持）"""
    return _clip01_base(x)


def _lazy_import(mod_path: str, attr: Optional[str] = None) -> Any:
    """ISSUE-4 style import isolation: never crash at import-time."""
    try:
        import importlib
        m = importlib.import_module(mod_path)
        return getattr(m, attr) if attr else m
    except Exception as e:
        _warn(f"[lazy_import] {mod_path}{'.'+attr if attr else ''} skipped: {e}")
        return None


# =========================================================
# Safe logging paths (do not crash import)
# =========================================================

def _safe_paths() -> Tuple[Path, Path, Path, Path]:
    """
    Return (LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG) safely.
    Prefer veritas_os.logging.paths if available; else fallback to repo-local dirs.
    Also allow env overrides:
      - VERITAS_LOG_DIR
      - VERITAS_DATASET_DIR
    """
    env_log = (os.getenv("VERITAS_LOG_DIR") or "").strip()
    env_ds = (os.getenv("VERITAS_DATASET_DIR") or "").strip()

    try:
        from veritas_os.logging import paths as lp  # type: ignore

        LOG_DIR = Path(env_log).resolve() if env_log else Path(getattr(lp, "LOG_DIR")).resolve()
        DATASET_DIR = Path(env_ds).resolve() if env_ds else Path(getattr(lp, "DATASET_DIR")).resolve()
        VAL_JSON = Path(getattr(lp, "VAL_JSON")).resolve()
        META_LOG = Path(getattr(lp, "META_LOG")).resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG
    except Exception as e:
        _warn(f"[WARN][pipeline] logging.paths import failed -> fallback: {repr(e)}")
        LOG_DIR = (Path(env_log).resolve() if env_log else (REPO_ROOT / "logs").resolve())
        DATASET_DIR = (Path(env_ds).resolve() if env_ds else (REPO_ROOT / "dataset").resolve())
        VAL_JSON = (LOG_DIR / "value_ema.json").resolve()
        META_LOG = (LOG_DIR / "meta.log").resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG


LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG = _safe_paths()


# =========================================================
# Value EMA persistence
# =========================================================

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    _HAS_ATOMIC_IO = True
except Exception:
    _atomic_write_json = None  # type: ignore
    _HAS_ATOMIC_IO = False


def _load_valstats() -> Dict[str, Any]:
    try:
        p = Path(VAL_JSON)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}


def _save_valstats(d: Dict[str, Any]) -> None:
    try:
        p = Path(VAL_JSON)
        p.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_ATOMIC_IO and _atomic_write_json is not None:
            _atomic_write_json(p, d, indent=2)
        else:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        return None


# =========================================================
# Alternatives deduplication
# =========================================================

def _dedupe_alts_fallback(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
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


def _dedupe_alts(alts: List[Dict[str, Any]], veritas_core: Any = None) -> List[Dict[str, Any]]:
    # Prefer kernel helper if present
    try:
        if veritas_core is not None and hasattr(veritas_core, "_dedupe_alts"):
            return veritas_core._dedupe_alts(alts)  # type: ignore
    except Exception:
        pass
    return _dedupe_alts_fallback(alts)


# =========================================================
# MemoryModel (classifier/vec) for boosting
# =========================================================

MEM_VEC = None
MEM_CLF = None


def predict_gate_label(_text: str) -> Dict[str, float]:
    return {"allow": 0.5}


def _mem_model_path() -> str:
    try:
        from veritas_os.core.models import memory_model as mm  # type: ignore
        for k in ("MODEL_FILE", "MODEL_PATH"):
            if hasattr(mm, k):
                return str(getattr(mm, k))
    except Exception:
        pass
    return ""


try:
    from veritas_os.core.models import memory_model as memory_model_core  # type: ignore

    MEM_VEC = getattr(memory_model_core, "MEM_VEC", None)
    MEM_CLF = getattr(memory_model_core, "MEM_CLF", None)

    if hasattr(memory_model_core, "predict_gate_label"):
        from veritas_os.core.models.memory_model import predict_gate_label as _pgl  # type: ignore

        def predict_gate_label(text: str) -> Dict[str, float]:
            try:
                d = _pgl(text)
                return d if isinstance(d, dict) else {"allow": 0.5}
            except Exception:
                return {"allow": 0.5}

except Exception:
    pass


def _allow_prob(text: str) -> float:
    d = predict_gate_label(text)
    try:
        return float(d.get("allow", 0.0))
    except Exception:
        return 0.0


# =========================================================
# Required modules check
# =========================================================

def _check_required_modules(veritas_core: Any, fuji_core: Any) -> None:
    """必須モジュールの存在を確認し、欠落時は明確なエラーを出す"""
    missing = []
    if veritas_core is None:
        missing.append("kernel")
    if fuji_core is None:
        missing.append("fuji")
    if missing:
        raise ImportError(
            f"[FATAL][pipeline] Required modules missing: {', '.join(missing)}. "
            "Pipeline cannot function without these core modules."
        )


# =========================================================
# Core decide wrapper
# =========================================================

async def call_core_decide(
    core_fn,
    context: Dict[str, Any] | None,
    query: str,
    alternatives: List[Dict[str, Any]] | None,
    min_evidence: int | None = None,
):
    """
    core_fn のシグネチャ差（kernel.decide / veritas_core.decide の揺れ）を吸収するラッパ。

    対応パターン:
    A) decide(ctx=..., options=..., min_evidence=..., query=...)
    B) decide(context=..., query=..., alternatives=..., min_evidence=...)
    C) decide(context, query, alternatives, min_evidence=?)
    """

    ctx = dict(context or {})
    ctx["query"] = query
    opts = list(alternatives or [])

    def _is_awaitable(x: Any) -> bool:
        return hasattr(x, "__await__")

    def _params(fn) -> set[str]:
        try:
            return set(inspect.signature(fn).parameters.keys())
        except Exception:
            return set()

    p = _params(core_fn)

    # ---- Try A: ctx/options style ----
    try:
        if ("ctx" in p) or ("options" in p):
            res = core_fn(ctx=ctx, options=opts, min_evidence=min_evidence, query=query)
            return await res if _is_awaitable(res) else res
    except TypeError:
        pass

    # ---- Try B: context/query/alternatives style ----
    try:
        kw = {}
        # context arg name
        if "context" in p:
            kw["context"] = ctx
        elif "ctx" in p:
            kw["ctx"] = ctx
        else:
            # fallback
            kw["context"] = ctx

        # alternatives arg name
        if "alternatives" in p:
            kw["alternatives"] = opts
        elif "options" in p:
            kw["options"] = opts
        else:
            # fallback
            kw["alternatives"] = opts

        if "query" in p:
            kw["query"] = query

        if "min_evidence" in p:
            kw["min_evidence"] = min_evidence

        res = core_fn(**kw)
        return await res if _is_awaitable(res) else res
    except TypeError:
        pass

    # ---- Try C: positional ----
    res = core_fn(ctx, query, opts, min_evidence)
    return await res if _is_awaitable(res) else res
