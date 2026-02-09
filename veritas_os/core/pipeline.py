# veritas_os/core/pipeline.py
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
VERITAS Decision Pipeline (core/pipeline.py)

ISSUE-4 / robustness goals:
- Import must be resilient (optional components must not crash import).
- Avoid circular import traps (avoid time_utils etc).
- run_decide_pipeline(req, request) is the single entrypoint used by FastAPI server.

Payload contracts restored (tests / server expectations):
- extras.metrics.mem_hits (int) always present
- extras.metrics.memory_evidence_count (int) always present
- extras.metrics.web_hits (int) always present
- extras.metrics.web_evidence_count (int) always present
- extras.fast_mode (bool) always present
- extras.metrics.fast_mode (bool) always present
- evidence may include web items when available
- extras.memory_meta.context.fast must reflect fast mode (tests may check)
- web_search payload normalized (ok/results)
- decision saved into MemoryOS with key prefix "decision_"
"""

import asyncio
import inspect
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

from .utils import (
    _safe_float,
    _clip01 as _clip01_base,
    _redact_text,
    redact_payload,
    utc_now,
    utc_now_iso_z,
)
from . import self_healing

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    _HAS_ATOMIC_IO = True
except Exception:
    _atomic_write_json = None  # type: ignore
    _HAS_ATOMIC_IO = False


try:
    from fastapi import Request
except Exception:  # tests may import pipeline without fastapi installed
    Request = Any  # type: ignore


# =========================================================
# repo root / time helpers
# =========================================================

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os

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

# utc_now / utc_now_iso_z は utils.py に統合済み（import 済み）


# =========================================================
# Safe imports (core modules)
# =========================================================
#
# モジュールカテゴリ:
# - REQUIRED: 必須。None の場合は Pipeline が機能しない
# - RECOMMENDED: 推奨。None でも最低限動くが機能低下
# - OPTIONAL: 任意。なくても正常動作
#
# ★ ISSUE-4 対応: インポート時にクラッシュしない設計を維持
# ★ ただし、REQUIRED モジュールが None の場合は実行時にエラー
# =========================================================

def _to_bool(v: Any) -> bool:
    """Convert value to bool (for env vars, config values, etc.)"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("0", "false", "no", "n", "off", ""):
            return False
        return s in ("1", "true", "yes", "y", "on")
    return False


def _warn(msg: str) -> None:
    """警告メッセージを出力（環境変数で抑制可能）。メッセージの接頭辞に応じてログレベルを自動選択する。"""
    if _to_bool(os.getenv("VERITAS_PIPELINE_WARN", "1")):
        if msg.startswith("[INFO]"):
            logger.info(msg)
        elif msg.startswith("[ERROR]") or msg.startswith("[FATAL]"):
            logger.error(msg)
        else:
            logger.warning(msg)


def _check_required_modules() -> None:
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


# ---- kernel (REQUIRED) ----
try:
    from . import kernel as veritas_core  # type: ignore
except Exception as e:  # pragma: no cover
    veritas_core = None  # type: ignore
    _warn(f"[ERROR][pipeline] kernel import failed (REQUIRED): {repr(e)}")

# ---- fuji (REQUIRED) ----
try:
    from . import fuji as fuji_core  # type: ignore
except Exception as e:  # pragma: no cover
    fuji_core = None  # type: ignore
    _warn(f"[ERROR][pipeline] fuji import failed (REQUIRED): {repr(e)}")

# ---- memory (RECOMMENDED) ----
try:
    from . import memory as mem  # type: ignore
except Exception as e:  # pragma: no cover
    mem = None  # type: ignore
    _warn(f"[WARN][pipeline] memory import failed (RECOMMENDED): {repr(e)}")

# ---- value_core (RECOMMENDED) ----
try:
    from . import value_core  # type: ignore
except Exception as e:  # pragma: no cover
    value_core = None  # type: ignore
    _warn(f"[WARN][pipeline] value_core import failed (RECOMMENDED): {repr(e)}")

# ---- world model (RECOMMENDED) ----
try:
    from . import world as world_model  # type: ignore
except Exception as e:  # pragma: no cover
    world_model = None  # type: ignore
    _warn(f"[WARN][pipeline] world import failed (RECOMMENDED): {repr(e)}")

# ---- reason (OPTIONAL) ----
try:
    from . import reason as reason_core  # type: ignore
except Exception as e:  # pragma: no cover
    reason_core = None  # type: ignore
    _warn(f"[INFO][pipeline] reason import failed (OPTIONAL): {repr(e)}")

# ---- debate (RECOMMENDED) ----
try:
    from . import debate as debate_core  # type: ignore
except Exception as e:  # pragma: no cover
    debate_core = None  # type: ignore
    _warn(f"[WARN][pipeline] debate import failed (RECOMMENDED): {repr(e)}")


# =========================================================
# Safe imports (API schemas / persona)
# =========================================================

try:
    from veritas_os.api.schemas import DecideRequest, DecideResponse  # type: ignore
except Exception as e:  # pragma: no cover
    DecideRequest = Any  # type: ignore
    DecideResponse = Any  # type: ignore
    _warn(f"[WARN][pipeline] api.schemas import failed: {repr(e)}")

try:
    from veritas_os.api.evolver import load_persona  # type: ignore
except Exception:  # pragma: no cover
    def load_persona() -> dict:  # type: ignore
        return {"name": "fallback", "mode": "minimal"}

try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii  # type: ignore
    _HAS_SANITIZE = True
except Exception:  # pragma: no cover
    _mask_pii = None  # type: ignore
    _HAS_SANITIZE = False


# =========================================================
# util helpers
# =========================================================

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


# _redact_text / redact_payload は utils.py に統合済み（import 済み）


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
# Safe dataset writer (optional)
# =========================================================

try:
    from veritas_os.logging.dataset_writer import build_dataset_record, append_dataset_record  # type: ignore
except Exception as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] dataset_writer import failed: {repr(e)}")

    def build_dataset_record(*, req_payload: dict, res_payload: dict, meta: dict, eval_meta: dict) -> dict:  # type: ignore
        return {"req": req_payload, "res": res_payload, "meta": meta, "eval": eval_meta}

    def append_dataset_record(_rec: dict) -> None:  # type: ignore
        return None


# =========================================================
# Trust log (optional; fallback-safe)
# =========================================================

try:
    from veritas_os.logging.trust_log import append_trust_log, write_shadow_decide  # type: ignore
except Exception:  # pragma: no cover
    def append_trust_log(_entry: dict) -> None:  # type: ignore
        return None

    def write_shadow_decide(  # type: ignore
        request_id: str,
        body: dict,
        chosen: dict,
        telos_score: float,
        fuji: dict,
    ) -> None:
        return None


# =========================================================
# Optional: MemoryModel (classifier/vec) for boosting
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
    except Exception as e:
        logger.debug("_save_valstats failed: %s", e)


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


def _dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Prefer kernel helper if present
    try:
        if veritas_core is not None and hasattr(veritas_core, "_dedupe_alts"):
            return veritas_core._dedupe_alts(alts)  # type: ignore
    except Exception:
        pass
    return _dedupe_alts_fallback(alts)


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



# =========================================================
# Memory adapter (supports mem.search OR mem.MEM.search)
# =========================================================

def _get_memory_store() -> Optional[Any]:
    if mem is None:
        return None
    # module-level functions
    if hasattr(mem, "search") or hasattr(mem, "put") or hasattr(mem, "get"):
        return mem
    # store object
    store = getattr(mem, "MEM", None)
    if store is not None:
        return store
    return None


def _call_with_accepted_kwargs(fn, kwargs: Dict[str, Any]) -> Any:
    """inspectで受け取れるkwargsだけ渡す（put/search/add_usageなどの差異吸収）"""
    try:
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        return fn(**filtered)
    except Exception:
        # signatureが取れない/壊れてる場合はそのまま投げる
        return fn(**kwargs)


def _memory_has(store: Any, name: str) -> bool:
    try:
        return callable(getattr(store, name))
    except Exception:
        return False


def _memory_search(store: Any, **kwargs: Any) -> Any:
    """
    Try best-effort to call store.search with varying signatures.
    """
    if not _memory_has(store, "search"):
        raise RuntimeError("memory.search not available")

    fn = getattr(store, "search")
    # 1) 可能なkwargsだけ渡す
    try:
        return _call_with_accepted_kwargs(fn, dict(kwargs))
    except TypeError:
        pass

    # 2) Minimal fallbacks
    q = kwargs.get("query")
    k = kwargs.get("k", 8)

    try:
        return fn(query=q, k=k)  # type: ignore
    except Exception:
        pass

    try:
        return fn(q, k)  # type: ignore
    except Exception:
        return fn(query=q)  # type: ignore


def _memory_put(store: Any, user_id: Any, *, key: str, value: Any, meta: Any = None) -> None:
    if not _memory_has(store, "put"):
        return None
    fn = getattr(store, "put")
    # 1) kwargs filtering
    try:
        _call_with_accepted_kwargs(
            fn,
            {"user_id": user_id, "key": key, "value": value, "meta": meta},
        )
        return None
    except Exception:
        pass

    # 2) positional variants
    try:
        fn(user_id, key=key, value=value, meta=meta)  # type: ignore
        return None
    except Exception:
        pass
    try:
        fn(user_id, key, value)  # type: ignore
        return None
    except Exception:
        pass
    try:
        fn(key, value)  # type: ignore
        return None
    except Exception:
        return None


def _memory_add_usage(store: Any, user_id: Any, cited_ids: List[str]) -> None:
    if not _memory_has(store, "add_usage"):
        return None
    fn = getattr(store, "add_usage")
    try:
        _call_with_accepted_kwargs(fn, {"user_id": user_id, "cited_ids": cited_ids})
        return None
    except Exception:
        pass
    try:
        fn(user_id, cited_ids)  # type: ignore
    except Exception:
        return None


# =========================================================
# Optional: WebSearch adapter (do not crash import)
# =========================================================

_tool_web_search = None
try:
    from veritas_os.tools.web_search import web_search as _tool_web_search  # type: ignore
except Exception:
    # optional dependency / env missing in CI or local
    _tool_web_search = None


async def _safe_web_search(query: str, *, max_results: int = 5) -> Optional[dict]:
    """Returns web_search result dict or None (never raises).
    Supports both sync/async web_search (tests often monkeypatch async).
    """
    fn = globals().get("web_search")
    if not callable(fn):
        fn = globals().get("_tool_web_search")
    if not callable(fn):
        return None

    try:
        ws = fn(query, max_results=max_results)  # type: ignore[misc]
        if inspect.isawaitable(ws):
            ws = await ws
        return ws if isinstance(ws, dict) else None
    except Exception:
        return None


def _normalize_web_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """
    web_search の戻り値を {"ok": bool, "results": list} に正規化する。
    tools.web_search の contract を基本として、異形も吸収する。
    """
    if payload is None:
        return None

    if isinstance(payload, dict):
        out = dict(payload)
        # results が無い/壊れている場合の救済
        if "results" not in out or not isinstance(out.get("results"), list):
            for k in ("items", "hits", "organic", "organic_results"):
                if isinstance(out.get(k), list):
                    out["results"] = out[k]
                    break
        out.setdefault("results", [])
        # ok が無ければ「取得できた扱い」で True
        if "ok" not in out:
            out["ok"] = True
        return out

    if isinstance(payload, list):
        return {"ok": True, "results": payload}

    s = str(payload)
    return {"ok": True, "results": [{"title": s, "url": "", "snippet": s}]}

# =========================================================
# evidence.py -> pipeline item
# =========================================================
try:
    from veritas_os.core import evidence as evidence_core  # type: ignore
except Exception as e:  # pragma: no cover
    evidence_core = None  # type: ignore
    _warn(f"[WARN][pipeline] evidence import failed (OPTIONAL): {repr(e)}")


def _norm_evidence_item_simple(ev: Any) -> Optional[Dict[str, Any]]:
    """Module-level evidence normalizer (lightweight shim).

    The full version lives inside the pipeline function as a nested def.
    This shim is used by ``_evidencepy_to_pipeline_item`` which is defined
    at module level and therefore cannot see the nested version.
    """
    if not isinstance(ev, dict):
        return None
    try:
        ev2 = dict(ev)
        if "confidence" not in ev2 and "weight" in ev2:
            ev2["confidence"] = ev2.get("weight")
        if ("title" not in ev2 or ev2.get("title") in (None, "")) and "kind" in ev2:
            ev2["title"] = f"local:{ev2.get('kind')}"
        if ("uri" not in ev2 or ev2.get("uri") in (None, "")) and "kind" in ev2:
            ev2["uri"] = f"internal:evidence:{ev2.get('kind')}"
        src = ev2.get("source") or "local"
        conf_raw = ev2.get("confidence", 0.7)
        conf = max(0.0, min(1.0, float(conf_raw if conf_raw is not None else 0.7)))
        snippet = ev2.get("snippet")
        snippet_s = "" if snippet is None else str(snippet)
        uri = ev2.get("uri")
        uri_s = str(uri) if uri is not None else None
        return {
            "source": str(src),
            "uri": uri_s,
            "title": str(ev2.get("title") or ""),
            "snippet": snippet_s,
            "confidence": conf,
        }
    except Exception:
        return None


def _evidencepy_to_pipeline_item(ev: dict) -> dict | None:
    return _norm_evidence_item_simple(
        {
            "source": ev.get("source", "local"),
            "uri": f"internal:evidence:{ev.get('kind','unknown')}",
            "title": f"local_{ev.get('kind','unknown')}",
            "snippet": ev.get("snippet", ""),
            "confidence": float(ev.get("weight", 0.5) or 0.5),
            "tags": ev.get("tags") or [],
        }
    )


# =========================================================
# main pipeline (FULL / hardened) - COMPLETE EDITION (DROP-IN)
# =========================================================

async def run_decide_pipeline(
    req: DecideRequest,
    request: Request,
) -> Dict[str, Any]:
    """
    Main pipeline for /v1/decide.
    Returns a dict payload compatible with DecideResponse.

    Hardened invariants:
      - extras.fast_mode always exists
      - extras.metrics.{mem_hits, memory_evidence_count, web_hits, web_evidence_count, fast_mode} always exist
      - extras.memory_meta.context.fast always exists
      - backward compat key: metrics.mem_evidence_count
      - import-time failures must not break the request (ISSUE-4 style lazy import)
    """

    # ★ 必須モジュールの存在確認（欠落時は明確なエラー）
    _check_required_modules()

    # -------------------------------
    # local helpers (contract hardening)
    # -------------------------------
    def _lazy_import(mod_path: str, attr: Optional[str] = None) -> Any:
        """ISSUE-4 style import isolation: never crash at import-time."""
        try:
            import importlib
            m = importlib.import_module(mod_path)
            return getattr(m, attr) if attr else m
        except Exception as e:
            _warn(f"[lazy_import] {mod_path}{'.'+attr if attr else ''} skipped: {e}")
            return None

    # -------------------------------
    # ISSUE-2: Critique required (audit hardening)  [COMPLETE / FINAL]
    #   - Critique must never be empty
    #   - critique MUST be dict (never list)  ✅（あなたの方針）
    #   - findings must have >= 3 items
    #   - normalize legacy/list/text payloads
    #   - never raise (best-effort)
    #
    # Usage (pipeline side):
    #   critique_obj = await _run_critique_best_effort(...)
    #   response["critique"] = _ensure_critique_required(..., critique_obj=critique_obj, ...)
    #   # NOTE: "append" しない。常に上書きで dict を格納。
    # -------------------------------
    
    
    # -------------------------------
    # tiny utils (no free vars / safe)
    # -------------------------------
    
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
    
    
    def _to_bool(x: Any) -> bool:
        if isinstance(x, bool):
            return x
        if x is None:
            return False
        if isinstance(x, (int, float)):
            return x != 0
        try:
            s = str(x).strip().lower()
        except Exception:
            return False
        return s in ("1", "true", "yes", "y", "on")
    
    
    def _as_str(x: Any, *, limit: int = 2000) -> str:
        try:
            s = "" if x is None else str(x)
        except Exception:
            s = repr(x)
        if limit and len(s) > limit:
            return s[:limit]
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
    
    
    def _set_int_metric(
        extras: Dict[str, Any],
        key: str,
        value: Any,
        default: int = 0,
    ) -> None:
        extras.setdefault("metrics", {})
        if not isinstance(extras["metrics"], dict):
            extras["metrics"] = {}
        try:
            extras["metrics"][key] = int(value)
        except Exception:
            extras["metrics"][key] = int(default)
    
    
    def _set_bool_metric(
        extras: Dict[str, Any],
        key: str,
        value: Any,
        default: bool = False,
    ) -> None:
        extras.setdefault("metrics", {})
        if not isinstance(extras["metrics"], dict):
            extras["metrics"] = {}
        try:
            extras["metrics"][key] = _to_bool(value)
        except Exception:
            extras["metrics"][key] = bool(default)
    
    
    # -------------------------------
    # ISSUE-2.5: Contract helpers (fix NameError + invariants)
    #   - Provide _ensure_full_contract to avoid NameError
    #   - NEVER references free vars -> safe
    # -------------------------------
    
    def _ensure_full_contract(
        extras: Dict[str, Any],
        *,
        fast_mode_default: bool,
        context_obj: Dict[str, Any],
        query_str: str = "",
    ) -> None:
        """
        Strong contract (safe, no free vars):
        - extras.fast_mode always exists (bool)
        - extras.metrics.{mem_hits, memory_evidence_count, web_hits, web_evidence_count, fast_mode} always exist
        - backward compat: metrics.mem_evidence_count
        - extras.env_tools always dict
        - extras.memory_meta always dict
        - extras.memory_meta.context always dict and has context.fast(bool)
        - extras.memory_meta.query filled if possible (query_str)
        """
        if not isinstance(extras, dict):
            return
    
        extras.setdefault("metrics", {})
        if not isinstance(extras["metrics"], dict):
            extras["metrics"] = {}
    
        extras.setdefault("env_tools", {})
        if not isinstance(extras["env_tools"], dict):
            extras["env_tools"] = {}
    
        extras.setdefault("memory_meta", {})
        if not isinstance(extras["memory_meta"], dict):
            extras["memory_meta"] = {}
    
        # fast_mode
        extras["fast_mode"] = _to_bool(extras.get("fast_mode", fast_mode_default))
        _set_bool_metric(
            extras,
            "fast_mode",
            (extras.get("metrics", {}) or {}).get("fast_mode", extras["fast_mode"]),
            default=extras["fast_mode"],
        )
    
        # ints
        _set_int_metric(extras, "mem_hits", extras["metrics"].get("mem_hits", 0), default=0)
        _set_int_metric(
            extras,
            "memory_evidence_count",
            extras["metrics"].get("memory_evidence_count", 0),
            default=0,
        )
        _set_int_metric(extras, "web_hits", extras["metrics"].get("web_hits", 0), default=0)
        _set_int_metric(
            extras,
            "web_evidence_count",
            extras["metrics"].get("web_evidence_count", 0),
            default=0,
        )
    
        # backward compat
        try:
            extras["metrics"].setdefault(
                "mem_evidence_count",
                int(extras["metrics"].get("mem_evidence_count", 0) or 0),
            )
        except Exception:
            extras["metrics"]["mem_evidence_count"] = 0
    
        # memory_meta.context merge
        mm = extras["memory_meta"]
        try:
            base_ctx = dict(context_obj) if isinstance(context_obj, dict) else {}
        except Exception:
            base_ctx = {}
    
        mm_ctx = mm.get("context")
        if not isinstance(mm_ctx, dict):
            mm_ctx = dict(base_ctx)
            mm["context"] = mm_ctx
        else:
            for k, v in base_ctx.items():
                mm_ctx.setdefault(k, v)
    
        # invariant: context.fast
        mm_ctx["fast"] = _to_bool(mm_ctx.get("fast", extras["fast_mode"]))
    
        # invariant: memory_meta.query
        try:
            existing_q = mm.get("query")
            if not (isinstance(existing_q, str) and existing_q.strip()):
                if isinstance(query_str, str) and query_str.strip():
                    mm["query"] = query_str
        except Exception:
            pass
    
    
    # -------------------------------
    # Critique enforcement core
    # -------------------------------
    
    def _default_findings() -> List[Dict[str, Any]]:
        """
        最低3項目を満たすための “監査の定番指摘”
        NOTE: fix は日本語で統一（UI一貫性）
        """
        return [
            {
                "severity": "med",
                "message": "Evidence coverage may be insufficient or not independently verified",
                "code": "CRITIQUE_EVIDENCE_COVERAGE",
                "fix": "一次ソース + 独立ソース2件以上で裏取りし、根拠を decision.evidence に紐付けてください。",
                "details": {"hint": "primary+independent", "min_sources": 3},
            },
            {
                "severity": "med",
                "message": "Assumptions / scope / constraints might be under-specified",
                "code": "CRITIQUE_SCOPE_UNSPECIFIED",
                "fix": "目的・スコープ・制約・禁止事項・KPI を context に固定してください。",
                "details": {"hint": "goal/scope/constraints/kpi"},
            },
            {
                "severity": "med",
                "message": "Alternatives / trade-offs are not fully compared",
                "code": "CRITIQUE_ALTERNATIVES_WEAK",
                "fix": "少なくとも2案を比較し、採用/不採用理由（トレードオフ）を明示してください。",
                "details": {"hint": "compare>=2", "include": ["pros", "cons", "tradeoffs"]},
            },
        ]
    
    
    def _pad_findings(findings: Any, *, min_items: int = 3) -> List[Dict[str, Any]]:
        """
        findings を List[Dict] に正規化 + min_items までパッド。
        例外は出さない。
        """
        out: List[Dict[str, Any]] = []
    
        if isinstance(findings, list):
            for it in findings:
                if isinstance(it, dict):
                    it2 = dict(it)
                    it2["severity"] = _norm_severity(it2.get("severity", "med"))
                    it2.setdefault(
                        "message",
                        it2.get("message")
                        or it2.get("issue")
                        or it2.get("msg")
                        or "Critique finding",
                    )
                    it2.setdefault("code", it2.get("code") or "CRITIQUE_GENERIC")
    
                    # details を dict 強制
                    if "details" in it2 and not isinstance(it2.get("details"), dict):
                        it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
    
                    # fix は任意
                    if "fix" in it2 and it2.get("fix") is not None:
                        it2["fix"] = _as_str(it2.get("fix"), limit=1000)
    
                    out.append(it2)
                else:
                    out.append(
                        {
                            "severity": "med",
                            "message": _as_str(it, limit=500),
                            "code": "CRITIQUE_TEXT",
                        }
                    )
    
        elif isinstance(findings, dict):
            it2 = dict(findings)
            it2["severity"] = _norm_severity(it2.get("severity", "med"))
            it2.setdefault(
                "message",
                it2.get("message") or it2.get("issue") or it2.get("msg") or "Critique finding",
            )
            it2.setdefault("code", it2.get("code") or "CRITIQUE_GENERIC")
    
            if "details" in it2 and not isinstance(it2.get("details"), dict):
                it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
    
            if "fix" in it2 and it2.get("fix") is not None:
                it2["fix"] = _as_str(it2.get("fix"), limit=1000)
    
            out = [it2]
    
        elif findings is not None:
            out = [
                {
                    "severity": "med",
                    "message": _as_str(findings, limit=500),
                    "code": "CRITIQUE_TEXT",
                }
            ]
    
        defaults = _default_findings()
        i = 0
        while len(out) < int(min_items):
            out.append(dict(defaults[i % len(defaults)]))
            i += 1
    
        # 最終固定（必須キー）
        fixed: List[Dict[str, Any]] = []
        for it in out:
            if not isinstance(it, dict):
                fixed.append(
                    {
                        "severity": "med",
                        "message": _as_str(it, limit=500),
                        "code": "CRITIQUE_TEXT",
                    }
                )
                continue
    
            it2 = dict(it)
            it2["severity"] = _norm_severity(it2.get("severity", "med"))
            it2["message"] = _as_str(it2.get("message") or "Critique finding", limit=1000)
            it2["code"] = _as_str(it2.get("code") or "CRITIQUE_GENERIC", limit=120)
    
            if "details" in it2 and not isinstance(it2.get("details"), dict):
                it2["details"] = {"raw": _as_str(it2.get("details"), limit=500)}
    
            fixed.append(it2)
    
        return fixed
    
    
    def _critique_fallback(
        *,
        reason: str,
        query: str = "",
        chosen: Any = None,
    ) -> Dict[str, Any]:
        """
        critique が取れない時の dict 契約 fallback（必ず findings>=3）
        """
        chosen_title = ""
        try:
            if isinstance(chosen, dict):
                chosen_title = _as_str(
                    chosen.get("title") or chosen.get("name") or chosen.get("chosen") or "",
                    limit=120,
                )
            elif chosen is not None:
                chosen_title = _as_str(chosen, limit=120)
        except Exception:
            chosen_title = ""
    
        findings = _pad_findings(
            [
                {
                    "severity": "high",
                    "message": "Critique unavailable -> auditability reduced",
                    "code": "CRITIQUE_MISSING",
                    "fix": "critique module / pipeline integration を確認し、再実行してください。",
                }
            ],
            min_items=3,
        )
    
        return {
            "ok": False,
            "mode": "fallback",
            "reason": _as_str(reason, limit=200),
            "summary": "Critique missing/failed. Manual review required.",
            "findings": findings,
            "recommendations": [
                "Re-run decision with critique enabled",
                "Inspect TrustLog for evidence/debate/gate consistency",
            ],
            "query": _as_str(query, limit=500),
            "chosen_title": chosen_title,
            "ts": _now_iso(),
        }
    
    
    def _list_to_findings(items: List[Any]) -> List[Dict[str, Any]]:
        """
        critique.analyze() の List[{'issue','severity','details','fix'}] を findings に変換
        """
        out: List[Dict[str, Any]] = []
        for it in items or []:
            if isinstance(it, dict):
                sev = _norm_severity(it.get("severity", "med"))
                issue = it.get("issue") or it.get("message") or it.get("msg") or "Critique finding"
                fix = it.get("fix")
                details = it.get("details") if isinstance(it.get("details"), dict) else {}
                out.append(
                    {
                        "severity": sev,
                        "message": _as_str(issue, limit=1000),
                        "code": _as_str(it.get("code") or "CRITIQUE_RULE", limit=120),
                        "details": details,
                        "fix": _as_str(fix, limit=1000) if fix is not None else None,
                    }
                )
            else:
                out.append(
                    {
                        "severity": "med",
                        "message": _as_str(it, limit=500),
                        "code": "CRITIQUE_TEXT",
                    }
                )
        return out
    
    
    def _normalize_critique_payload(x: Any, *, min_findings: int = 3) -> Dict[str, Any]:
        """
        Normalize critique to dict ALWAYS (never raise).
        Enforce findings >= min_findings.
    
        Accepts:
          - dict: passthrough + defaults + findings padding
          - list: treat as critique items list -> findings
          - str/other: wrap as text finding
          - None: returns {} (caller will fallback)
        """
        if x is None:
            return {}
    
        # legacy: list -> dict
        if isinstance(x, list):
            findings = _pad_findings(_list_to_findings(x), min_items=min_findings)
            return {
                "ok": True,
                "mode": "legacy_list",
                "summary": "Critique generated (legacy list normalized).",
                "findings": findings,
                "recommendations": [],
                "ts": _now_iso(),
            }
    
        # dict -> dict (enforce schema)
        if isinstance(x, dict):
            out = dict(x)
    
            if "ok" not in out:
                out["ok"] = True
    
            out.setdefault("mode", out.get("mode") or "normal")
            out.setdefault("ts", out.get("ts") or _now_iso())
            out.setdefault("summary", out.get("summary") or "Critique generated.")
    
            # findings extraction fallbacks
            findings = out.get("findings")
            if findings is None:
                if isinstance(out.get("items"), list):
                    findings = _list_to_findings(out["items"])
                elif isinstance(out.get("issues"), list):
                    findings = _list_to_findings(out["issues"])
                else:
                    findings = []
    
            out["findings"] = _pad_findings(findings, min_items=min_findings)
    
            rec = out.get("recommendations")
            if rec is None:
                out["recommendations"] = []
            elif not isinstance(rec, list):
                out["recommendations"] = [_as_str(rec, limit=500)]
    
            return out
    
        # text/other -> dict
        s = _as_str(x, limit=1000)
        findings = _pad_findings(
            [{"severity": "med", "message": s, "code": "CRITIQUE_TEXT"}],
            min_items=min_findings,
        )
        return {
            "ok": True,
            "mode": "text",
            "summary": "Critique normalized from text.",
            "findings": findings,
            "recommendations": [],
            "ts": _now_iso(),
        }
    
    
    def _ensure_critique_required(
        *,
        response_extras: Dict[str, Any],
        query: str,
        chosen: Any,
        critique_obj: Any,
        min_findings: int = 3,
    ) -> Dict[str, Any]:
        """
        Enforce:
          - critique ALWAYS exists and is dict
          - critique.findings ALWAYS list and >= min_findings
    
        Side effects:
          - extras.env_tools.critique_degraded = True when fallback used
          - extras.metrics.critique_findings_count / critique_ok
        """
        c = _normalize_critique_payload(critique_obj, min_findings=min_findings)
        if not isinstance(c, dict) or not c:
            c = _critique_fallback(reason="missing_in_response", query=query, chosen=chosen)
    
        # hard enforce (even if caller passed weird payload)
        c["findings"] = _pad_findings(c.get("findings"), min_items=min_findings)
    
        used_fallback = bool(c.get("ok") is False) or (c.get("mode") == "fallback")
        if used_fallback:
            response_extras.setdefault("env_tools", {})
            if isinstance(response_extras["env_tools"], dict):
                response_extras["env_tools"]["critique_degraded"] = True
    
        response_extras.setdefault("metrics", {})
        if isinstance(response_extras["metrics"], dict):
            response_extras["metrics"]["critique_findings_count"] = len(c.get("findings") or [])
            response_extras["metrics"]["critique_ok"] = bool(c.get("ok") is True)
    
        # (Optional) keep small trace
        c.setdefault("query", _as_str(query, limit=500))
        return c
    
    
    def _chosen_to_option(chosen: Any) -> Dict[str, Any]:
        """
        critique.analyze() に渡す option を chosen から合成（壊れない）
        """
        opt: Dict[str, Any] = {}
    
        if isinstance(chosen, dict):
            opt["title"] = chosen.get("title") or chosen.get("name") or chosen.get("chosen") or "chosen"
            for k in ("risk", "complexity", "value", "feasibility", "timeline"):
                if k in chosen:
                    opt[k] = chosen.get(k)
    
            score = chosen.get("score")
            if isinstance(score, dict):
                for k in ("risk", "value", "feasibility"):
                    if k not in opt and k in score:
                        opt[k] = score.get(k)
        else:
            opt["title"] = _as_str(chosen, limit=120) if chosen is not None else "chosen"
    
        opt["title"] = _as_str(opt.get("title") or "chosen", limit=120)
        return opt
    
    
    async def _run_critique_best_effort(
        *,
        query: str,
        chosen: Any,
        evidence: List[Dict[str, Any]],
        debate: Any,
        context: Dict[str, Any],
        user_id: str,
        min_findings: int = 3,
    ) -> Dict[str, Any]:
        """
        Try to generate critique via core module if available.
        Never raises; returns normalized dict with findings>=min_findings.
    
        IMPORTANT:
          - analyze() が list を返してもここで dict へ正規化する
          - pipeline は response["critique"] = returned_dict を “上書き” で格納する
        """
        # NOTE: _lazy_import はあなたのコードベース側のユーティリティ想定
        crit_mod = _lazy_import("veritas_os.core.critique", None)
        if crit_mod is None:
            return _critique_fallback(reason="critique_module_missing", query=query, chosen=chosen)
    
        # 推奨: core 側に analyze_dict があればそれを優先（dict契約を直接得る）
        fn_dict = getattr(crit_mod, "analyze_dict", None)
        fn_list = getattr(crit_mod, "analyze", None)
    
        option = _chosen_to_option(chosen)
    
        try:
            if callable(fn_dict):
                out = fn_dict(option, evidence, context, min_items=min_findings)  # dict contract
                norm = _normalize_critique_payload(out, min_findings=min_findings)
            elif callable(fn_list):
                out = fn_list(option, evidence, context)  # list contract (legacy)
                norm = _normalize_critique_payload(out, min_findings=min_findings)
            else:
                return _critique_fallback(reason="critique_analyze_missing", query=query, chosen=chosen)
    
            if not norm:
                return _critique_fallback(reason="critique_returned_empty", query=query, chosen=chosen)
    
            norm["findings"] = _pad_findings(norm.get("findings"), min_items=min_findings)
            norm.setdefault("summary", norm.get("summary") or "Critique generated.")
            norm.setdefault("recommendations", norm.get("recommendations") or [])
            norm.setdefault("mode", norm.get("mode") or "normal")
            norm.setdefault("ts", norm.get("ts") or _now_iso())
    
            return norm
    
        except Exception as e:
            # best-effort: never raise
            return _critique_fallback(
                reason=f"exception:{type(e).__name__}",
                query=query,
                chosen=chosen,
            )



    # -------------------------------
    # ISSUE-2.6: Web results extractor (contract hardening)
    #   - Some pipelines expect _extract_web_results(ws)
    #   - Must never raise
    #   - Absorb many shapes: dict/list/nested {data:{results:[]}} etc.
    # -------------------------------
    def _extract_web_results(ws: Any) -> List[Any]:
        """
        web_search の戻りがどんな形でも「結果リスト」を吸い上げる。
        - ws が list: そのまま返す
        - ws が dict: results/items/data/hits を優先探索
        - nested dict にも対応（1段〜2段）
        - それ以外は []
        """
        try:
            if ws is None:
                return []
            if isinstance(ws, list):
                return ws

            if not isinstance(ws, dict):
                return []

            # 1st pass: top-level common keys
            for k in ("results", "items", "data", "hits"):
                v = ws.get(k)
                if isinstance(v, list):
                    return v

            # 2nd pass: if values are dict, look one layer deeper
            for k in ("results", "items", "data", "hits"):
                v = ws.get(k)
                if isinstance(v, dict):
                    for kk in ("results", "items", "data", "hits"):
                        vv = v.get(kk)
                        if isinstance(vv, list):
                            return vv

            # 3rd pass: any nested dict under typical wrappers
            # e.g. {"ok":true,"output":{"results":[...]}}
            for k, v in ws.items():
                if isinstance(v, dict):
                    for kk in ("results", "items", "data", "hits"):
                        vv = v.get(kk)
                        if isinstance(vv, list):
                            return vv
                    # one more nested level
                    for k2, v2 in v.items():
                        if isinstance(v2, dict):
                            for kk in ("results", "items", "data", "hits"):
                                vv = v2.get(kk)
                                if isinstance(vv, list):
                                    return vv
        except Exception:
            return []

        return []

    # -------------------------------
    # ISSUE-2.7: Evidence normalizer / deduper (contract hardening)
    #   - Some pipelines expect _norm_evidence_item / _dedupe_evidence
    #   - Must never raise
    #   - Accept legacy evidence.py style:
    #       {source, kind, weight, snippet, tags}
    #     -> pipeline contract:
    #       {source, uri, title, snippet, confidence}
    # -------------------------------
    def _norm_evidence_item(ev: Any) -> Optional[Dict[str, Any]]:
        """Normalize evidence entries to dict; never raise.
        Accepts both pipeline-contract evidence and legacy/local evidence.py style:
          - confidence <- weight (if confidence missing)
          - title/uri synthesized from kind (if missing)
        """
        if not isinstance(ev, dict):
            return None

        try:
            ev2 = dict(ev)

            # ---- compat: evidence.py style -> pipeline contract ----
            # evidence.py: {source, kind, weight, snippet, tags}
            if "confidence" not in ev2 and "weight" in ev2:
                try:
                    ev2["confidence"] = ev2.get("weight")
                except Exception:
                    pass

            if ("title" not in ev2 or ev2.get("title") in (None, "")) and "kind" in ev2:
                try:
                    ev2["title"] = f"local:{ev2.get('kind')}"
                except Exception:
                    pass

            if ("uri" not in ev2 or ev2.get("uri") in (None, "")) and "kind" in ev2:
                try:
                    ev2["uri"] = f"internal:evidence:{ev2.get('kind')}"
                except Exception:
                    pass

            # ---- core normalize ----
            src = ev2.get("source")
            if src in (None, ""):
                src = "local"

            uri = ev2.get("uri")
            title = ev2.get("title") or ""

            snippet = ev2.get("snippet")
            try:
                snippet_s = "" if snippet is None else str(snippet)
            except Exception:
                snippet_s = repr(snippet)

            conf_raw = ev2.get("confidence", 0.7)
            try:
                conf = float(conf_raw if conf_raw is not None else 0.7)
            except Exception:
                conf = 0.7
            conf = max(0.0, min(1.0, conf))

            # uri は外部契約的に str に統一（dedupe/serialize 安定）
            if uri is None:
                uri_s = None
            else:
                try:
                    uri_s = str(uri)
                except Exception:
                    uri_s = repr(uri)

            return {
                "source": str(src),
                "uri": uri_s,
                "title": str(title),
                "snippet": snippet_s,
                "confidence": conf,
            }
        except Exception:
            return None

    def _dedupe_evidence(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stable dedupe for evidence list; never raise."""
        try:
            seen: set[tuple[str, str, str, str]] = set()
            out: List[Dict[str, Any]] = []
            for ev in evs:
                if not isinstance(ev, dict):
                    continue
                k = (
                    str(ev.get("source") or ""),
                    str(ev.get("uri") or ""),
                    str(ev.get("title") or ""),
                    str(ev.get("snippet") or ""),
                )
                if k in seen:
                    continue
                seen.add(k)
                out.append(ev)
            return out
        except Exception:
            return []

    # -------------------------------
    # ISSUE-2.8: Extras contract merger (contract hardening)
    #   - Some pipelines expect _merge_extras_preserving_contract
    #   - Must never raise
    #   - Must preserve metrics/memory_meta invariants
    # -------------------------------
    def _deep_merge_dict(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
        """Safe deep merge: dict-only. Never raises."""
        try:
            if not isinstance(dst, dict) or not isinstance(src, dict):
                return dst
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    _deep_merge_dict(dst[k], v)  # type: ignore[index]
                else:
                    dst[k] = v
            return dst
        except Exception:
            return dst

    def _merge_extras_preserving_contract(
        base_extras: Dict[str, Any],
        incoming_extras: Dict[str, Any],
        *,
        fast_mode_default: bool,
        context_obj: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge extras without losing contract keys.
        - metrics merged deeply (never replaced by non-dict)
        - memory_meta.context preserved and fast injected
        - never raises
        """
        try:
            if not isinstance(base_extras, dict):
                base_extras = {}
            if not isinstance(incoming_extras, dict):
                _ensure_full_contract(
                    base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
                )
                return base_extras

            prev_metrics = base_extras.get("metrics")
            prev_mm = base_extras.get("memory_meta")
            prev_fast = base_extras.get("fast_mode", fast_mode_default)

            _deep_merge_dict(base_extras, incoming_extras)

            if not isinstance(base_extras.get("metrics"), dict):
                base_extras["metrics"] = prev_metrics if isinstance(prev_metrics, dict) else {}
            if not isinstance(base_extras.get("memory_meta"), dict):
                try:
                    base_extras["memory_meta"] = (
                        prev_mm if isinstance(prev_mm, dict) else {"context": dict(context_obj)}
                    )
                except Exception:
                    base_extras["memory_meta"] = {"context": {}}

            base_extras["fast_mode"] = _to_bool(base_extras.get("fast_mode", prev_fast))

            _ensure_full_contract(
                base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
            )
            return base_extras
        except Exception:
            try:
                if isinstance(base_extras, dict):
                    _ensure_full_contract(
                        base_extras, fast_mode_default=fast_mode_default, context_obj=context_obj
                    )
                    return base_extras
            except Exception:
                pass
            return base_extras if isinstance(base_extras, dict) else {}





    # -------------------------------
    # start
    # -------------------------------
    started_at = time.time()
    body = req.model_dump() if hasattr(req, "model_dump") else _to_dict(req)
    if not isinstance(body, dict):
        body = {}

    # ---------- SAFE INIT ----------
    evidence: List[Dict[str, Any]] = []
    critique: Dict[str, Any] = {}
    debate: List[Any] = []
    telos: float = 0.0
    fuji_dict: Dict[str, Any] = {}
    alternatives: List[Dict[str, Any]] = []
    modifications: List[Any] = []

    # --------- Metrics contract (ALWAYS present) ----------
    response_extras: Dict[str, Any] = {
        "metrics": {
            "mem_hits": 0,
            "memory_evidence_count": 0,
            "web_hits": 0,
            "web_evidence_count": 0,
            "fast_mode": False,
            "mem_evidence_count": 0,  # backward compat
        },
        "fast_mode": False,
        "env_tools": {},
    }

    # ---------- Query / Context / user_id ----------
    context: Dict[str, Any] = body.get("context") or {}
    if not isinstance(context, dict):
        context = {}

    raw_query = body.get("query") or context.get("query") or ""
    if not isinstance(raw_query, str):
        raw_query = str(raw_query)
    query = raw_query.strip()

    # ★重要: user_idは必ず str 化（MemoryOS / WorldModel / logs が壊れない）
    user_id_raw = context.get("user_id") or body.get("user_id") or "anon"
    user_id = str(user_id_raw) if user_id_raw is not None else "anon"

    # ---------- fast mode (restore contract) ----------
    params = _get_request_params(request)
    fast_from_body = _to_bool(body.get("fast"))
    _ctx_mode = context.get("mode")
    fast_from_ctx = _to_bool(context.get("fast")) or (
        isinstance(_ctx_mode, str) and _ctx_mode.lower() == "fast"
    )
    fast_from_query = _to_bool(params.get("fast"))

    fast_mode = bool(fast_from_body or fast_from_ctx or fast_from_query)
    context["fast"] = bool(fast_mode)
    if fast_mode:
        context.setdefault("mode", "fast")
        body["fast"] = True

    response_extras["fast_mode"] = fast_mode
    response_extras["metrics"]["fast_mode"] = fast_mode
    response_extras["memory_meta"] = {"context": dict(context)}

    # ---------- WorldOS: inject state ----------
    world_model = _lazy_import("veritas_os.core.world", None) or _lazy_import("veritas_os.core.world_model", None)
    try:
        if world_model is not None and hasattr(world_model, "inject_state_into_context"):
            context = world_model.inject_state_into_context(context, user_id)  # type: ignore
            body["context"] = context
    except Exception as e:
        _warn(f"[WorldOS] inject_state_into_context skipped: {e}")

    # context 差し替え後に memory_meta を追従
    try:
        response_extras["memory_meta"] = {"context": dict(context)}
    except Exception:
        pass

    # ---- contract hardening (early)
    _ensure_full_contract(response_extras, fast_mode_default=fast_mode, context_obj=context, query_str=query)

    qlower = query.lower()
    is_veritas_query = any(k in qlower for k in ["veritas", "agi", "protoagi", "プロトagi", "veritasのagi化"])

    # ---------- PlannerOS ----------
    plan: Dict[str, Any] = {"steps": [], "raw": None, "source": "fallback"}
    try:
        plan_for_veritas_agi = _lazy_import("veritas_os.core.planner", "plan_for_veritas_agi")
        if callable(plan_for_veritas_agi):
            p = plan_for_veritas_agi(context=context, query=query)  # type: ignore[misc]
            if isinstance(p, dict):
                plan = p or plan
        _warn(f"[PlannerOS] steps={len(plan.get('steps', []))}, source={plan.get('source')}")
    except Exception as e:
        _warn(f"[PlannerOS] skipped: {e}")

    response_extras["planner"] = {
        "steps": plan.get("steps", []) if isinstance(plan, dict) else [],
        "raw": plan.get("raw") if isinstance(plan, dict) else None,
        "source": plan.get("source") if isinstance(plan, dict) else "fallback",
    }

    # ---------- Request id / min evidence ----------
    request_id = body.get("request_id") or secrets.token_hex(16)
    try:
        min_ev = int(body.get("min_evidence") or 1)
    except Exception:
        min_ev = 1
    if min_ev < 1:
        min_ev = 1

    # =========================================================
    # MemoryOS retrieval (best-effort) + contracts
    # =========================================================
    retrieved: List[Dict[str, Any]] = []
    want_doc = False
    raw_memory_kinds = context.get("memory_kinds") or body.get("memory_kinds")

    if isinstance(raw_memory_kinds, list):
        lowered = {str(k).lower() for k in raw_memory_kinds}
        want_doc = "doc" in lowered

    if is_veritas_query or any(key in qlower for key in ["論文", "paper", "zenodo", "veritas os", "protoagi", "プロトagi"]):
        want_doc = True

    memory_store = _get_memory_store()
    if query and memory_store is not None:
        try:
            mem_hits_raw = _memory_search(
                memory_store,
                query=query,
                k=8,
                kinds=["semantic", "skills", "episodic", "doc"],
                min_sim=MIN_MEMORY_SIMILARITY,
                user_id=user_id,
            )

            doc_hits_raw = None
            if want_doc:
                try:
                    doc_hits_raw = _memory_search(memory_store, query=query, k=5, kinds=["doc"], user_id=user_id)
                except Exception:
                    doc_hits_raw = None

            flat_hits: List[Dict[str, Any]] = []

            def _append_hits(src: Any, default_kind: Optional[str] = None) -> None:
                if not src:
                    return
                if isinstance(src, dict):
                    for kind, hits in src.items():
                        if not isinstance(hits, list):
                            continue
                        for h in hits:
                            if not isinstance(h, dict):
                                continue
                            h2 = dict(h)
                            h2.setdefault("kind", kind or default_kind or "episodic")
                            flat_hits.append(h2)
                elif isinstance(src, list):
                    for h in src:
                        if not isinstance(h, dict):
                            continue
                        h2 = dict(h)
                        if default_kind and not h2.get("kind"):
                            h2["kind"] = default_kind
                        flat_hits.append(h2)

            _append_hits(mem_hits_raw)
            _append_hits(doc_hits_raw, default_kind="doc")

            seen_ids: set[str] = set()
            deduped: List[Dict[str, Any]] = []
            for h in flat_hits:
                _id = h.get("id") or h.get("key")
                _id_s = str(_id) if _id is not None else ""
                if _id_s:
                    if _id_s in seen_ids:
                        continue
                    seen_ids.add(_id_s)
                deduped.append(h)

            for h in deduped:
                v = h.get("value") or {}
                text = h.get("text") or v.get("text") or v.get("query") or ""
                if not text:
                    continue
                kind = h.get("kind") or (h.get("meta") or {}).get("kind") or "episodic"
                retrieved.append(
                    {
                        "id": h.get("id") or h.get("key"),
                        "kind": kind,
                        "text": text,
                        "score": float(h.get("score", 0.5)),
                    }
                )

            retrieved.sort(key=lambda r: r.get("score", 0.0), reverse=True)
            response_extras["metrics"]["mem_hits"] = int(len(retrieved))

            if want_doc:
                doc_only = [r for r in retrieved if r.get("kind") == "doc"]
                non_doc = [r for r in retrieved if r.get("kind") != "doc"]
                top_hits = doc_only[:3] + non_doc[: max(0, 3 - len(doc_only[:3]))]
            else:
                top_hits = retrieved[:3]

            response_extras["metrics"]["memory_evidence_count"] = int(len(top_hits))

            for r in top_hits:
                text = r.get("text") or ""
                snippet = text[:200] + ("..." if len(text) > 200 else "")
                conf = max(0.3, min(1.0, float(r.get("score", 0.5))))
                if r.get("kind") == "doc" and conf < DOC_MIN_CONFIDENCE:
                    conf = DOC_MIN_CONFIDENCE
                ev = _norm_evidence_item(
                    {
                        "source": f"memory:{r.get('kind','')}",
                        "uri": r.get("id"),
                        "snippet": snippet,
                        "confidence": conf,
                    }
                )
                if ev:
                    evidence.append(ev)

            # record memory usage (best-effort)
            try:
                cited_ids = [str(r.get("id")) for r in top_hits if r.get("id")]
                if cited_ids:
                    ts = utc_now_iso_z()
                    _memory_put(
                        memory_store,
                        user_id,
                        key=f"memory_use_{ts}",
                        value={"used": True, "query": query, "citations": cited_ids, "timestamp": ts},
                    )
                    _memory_add_usage(memory_store, user_id, cited_ids)
            except Exception:
                pass

        except Exception as e:
            _warn(f"[AGI-Retrieval] memory retrieval error: {repr(e)}")
            response_extras.setdefault("env_tools", {})
            response_extras["env_tools"]["memory_error"] = repr(e)

    memory_citations_list: List[Dict[str, Any]] = []
    for r in retrieved[:10]:
        cid = r.get("id")
        if cid:
            memory_citations_list.append({"id": cid, "kind": r.get("kind"), "score": float(r.get("score", 0.0))})
    response_extras["memory_citations"] = memory_citations_list
    response_extras["memory_used_count"] = int(len(memory_citations_list))

    # =========================================================
    # WebSearch (optional / best-effort) + contract  [COMPLETE+ANCHOR]
    # =========================================================
    web_evidence: List[Dict[str, Any]] = []
    web_evidence_added = 0

    if not isinstance(evidence, list):
        evidence = list(evidence or [])

    web_explicit = _to_bool(body.get("web")) or _to_bool(context.get("web")) or _to_bool(params.get("web"))
    want_web = web_explicit or bool(is_veritas_query) or any(
        k in qlower for k in ["agi", "research", "論文", "paper", "zenodo", "arxiv"]
    )

    web_max = body.get("web_max_results") or context.get("web_max_results") or 5
    try:
        web_max = int(web_max)
    except Exception:
        web_max = 5
    web_max = max(1, min(20, web_max))

    response_extras.setdefault("metrics", {})
    if not isinstance(response_extras["metrics"], dict):
        response_extras["metrics"] = {}
    response_extras["metrics"].setdefault("web_hits", 0)
    response_extras["metrics"].setdefault("web_evidence_count", 0)

    should_run_web = bool(query and want_web and (not fast_mode or web_explicit or is_veritas_query))

    if should_run_web:
        ws = None
        ws_final_query = query  # ★ evidence に残す最終query（アンカー後が来る想定）

        try:
            ws0 = await _safe_web_search(query, max_results=web_max)

            ws = _normalize_web_payload(ws0)

        except Exception as e:
            response_extras.setdefault("env_tools", {})
            if isinstance(response_extras["env_tools"], dict):
                response_extras["env_tools"]["web_search_error"] = repr(e)

        if ws is None:
            # CI / offline / tool-missing でも contract を満たす（attempted=True）
            response_extras["web_search"] = {"ok": True, "results": [], "degraded": True}

            ev_fallback = _norm_evidence_item(
                {
                    "source": "web",
                    "uri": "web:search",
                    "title": "web_search attempted (degraded)",
                    # ★ evidence に query を残す（アンカー後が取れないのでここは query）
                    "snippet": f"[q={ws_final_query}] web_search unavailable or returned None",
                    "confidence": DEFAULT_CONFIDENCE,
                }
            )
            if ev_fallback:
                ev_fallback["source"] = "web"  # ★テスト契約: 必須
                web_evidence.append(ev_fallback)
                evidence.append(ev_fallback)
                web_evidence_added = 1

        else:
            # normalize が ok を落とすケースを防ぐ（results があるなら ok=True 扱い）
            if isinstance(ws, dict) and "ok" not in ws:
                ws["ok"] = True

            # ★最重要: アンカー後の確定クエリを ws.meta.final_query から取得し、以降これを使う
            try:
                meta = ws.get("meta") if isinstance(ws, dict) else None
                if isinstance(meta, dict):
                    ws_final_query = (
                        meta.get("final_query")
                        or meta.get("boosted_query")
                        or ws_final_query
                    )
                    # ★古いweb_search実装でも evidence 側が困らないように final_query を補完
                    meta.setdefault("final_query", ws_final_query)
            except Exception:
                ws_final_query = query

            response_extras["web_search"] = ws

            results = _extract_web_results(ws)
            response_extras["metrics"]["web_hits"] = int(len(results))

            for item in results[:3]:
                if isinstance(item, str):
                    item = {"title": item, "snippet": item}
                elif not isinstance(item, dict):
                    item = {"title": str(item), "snippet": str(item)}

                uri = item.get("url") or item.get("uri") or item.get("link") or item.get("href")
                title = item.get("title") or item.get("name") or ""
                snippet = item.get("snippet") or item.get("text") or title or (str(uri) if uri else "")

                # ★ evidence に必ずアンカー後queryを残す（今回破れていた箇所）
                snippet = f"[q={ws_final_query}] {snippet}"

                try:
                    confidence = float(item.get("confidence", 0.7) or 0.7)
                except Exception:
                    confidence = 0.7

                ev = _norm_evidence_item(
                    {
                        "source": "web",
                        "uri": uri,
                        "title": title,
                        "snippet": snippet,
                        "confidence": confidence,
                    }
                )
                if ev:
                    ev["source"] = "web"  # ★テスト契約: 必須
                    web_evidence.append(ev)
                    evidence.append(ev)
                    web_evidence_added += 1

            # ok=True なのに抽出0件 → 最低1件は入れる
            try:
                ok_flag = bool(ws.get("ok")) if isinstance(ws, dict) else False
            except Exception:
                ok_flag = False

            if ok_flag and web_evidence_added == 0:
                ev_fallback = _norm_evidence_item(
                    {
                        "source": "web",
                        "uri": "web:search",
                        "title": "web_search executed",
                        # ★ここもアンカー後 query を残す
                        "snippet": f"[q={ws_final_query}] web_search ok=True but no structured results extracted",
                        "confidence": DEFAULT_CONFIDENCE,
                    }
                )
                if ev_fallback:
                    ev_fallback["source"] = "web"
                    web_evidence.append(ev_fallback)
                    evidence.append(ev_fallback)
                    web_evidence_added = 1

    else:
        if want_web and "web_search" not in response_extras:
            response_extras["web_search"] = {
                "ok": False,
                "results": [],
                "skipped": True,
                "reason": "fast_mode",
            }

    response_extras["metrics"]["web_evidence_count"] = int(web_evidence_added)

    # =========================================================
    # options normalization + planner→alts for veritas queries
    # =========================================================
    explicit_raw = body.get("options") or body.get("alternatives") or []
    if not isinstance(explicit_raw, list):
        explicit_raw = []

    explicit_options: List[Dict[str, Any]] = [
        _norm_alt(a) for a in explicit_raw if isinstance(a, dict)
    ]
    explicit_options = [a for a in explicit_options if isinstance(a, dict)]  # safety

    # input_alts は「最終的に core に渡す alternatives」
    input_alts: List[Dict[str, Any]] = list(explicit_options)

    # 明示が無い場合だけ planner からステップを alternatives 化（veritas query 限定）
    if not input_alts and is_veritas_query:
        step_alts: List[Dict[str, Any]] = []
        for i, st in enumerate((plan.get("steps") if isinstance(plan, dict) else []) or [], 1):
            if not isinstance(st, dict):
                continue
            title = st.get("title") or st.get("name") or f"Step {i}"
            detail = st.get("detail") or st.get("description") or st.get("why") or ""
            step_alts.append(
                _norm_alt(
                    {
                        "id": st.get("id") or f"plan_step_{i}",
                        "title": title,
                        "description": detail,
                        "score": 1.0,
                        "meta": {"source": "planner", "step_index": i},
                    }
                )
            )

        input_alts = step_alts or [
            _norm_alt(
                {
                    "id": "veritas_mvp_demo",
                    "title": "MVPデモを最短で見せられる形にする",
                    "description": "Swagger/CLIで /v1/decide の30〜60秒デモを作る。",
                }
            ),
            _norm_alt(
                {
                    "id": "veritas_report",
                    "title": "技術監査レポートを仕上げる",
                    "description": "第三者が読めるレベルにブラッシュアップする。",
                }
            ),
            _norm_alt(
                {
                    "id": "veritas_spec_sheet",
                    "title": "MVP仕様書を1枚にまとめる",
                    "description": "CLI/API・FUJI・Debate・Memoryの流れを1枚に整理する。",
                }
            ),
            _norm_alt(
                {
                    "id": "veritas_demo_script",
                    "title": "第三者向けデモ台本を作る",
                    "description": "画面順・説明順・想定QAを台本化する。",
                }
            ),
        ]

    # alternatives の初期値は input_alts（= 明示 or planner）
    alternatives: List[Dict[str, Any]] = list(input_alts)

    if not isinstance(web_evidence, list):
        web_evidence = []

    # =========================================================
    # call kernel.decide (core)  ※ISSUE-4: lazy import
    # =========================================================
    veritas_core = _lazy_import("veritas_os.core.kernel", None) or _lazy_import("veritas_os.core", "kernel")
    debate_core = _lazy_import("veritas_os.core.debate", None) or _lazy_import("veritas_os.core", "debate")
    reason_core = _lazy_import("veritas_os.core.reason", None) or _lazy_import("veritas_os.core", "reason")
    fuji_core = _lazy_import("veritas_os.core.fuji", None) or _lazy_import("veritas_os.core", "fuji")
    value_core = _lazy_import("veritas_os.core.value_core", None) or _lazy_import("veritas_os.core", "value_core")

    core_decide = None
    try:
        if veritas_core is not None and hasattr(veritas_core, "decide"):
            core_decide = veritas_core.decide  # type: ignore[attr-defined]
    except Exception:
        core_decide = None

    raw = {}
    healing_attempts: List[Dict[str, Any]] = []
    healing_stop_reason: Optional[str] = None
    healing_enabled = self_healing.is_healing_enabled(context or {})
    healing_state = self_healing.HealingState()
    healing_budget = self_healing.HealingBudget()
    prev_healing_input: Optional[Dict[str, Any]] = None

    def _extract_rejection(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fuji_payload = payload.get("fuji") if isinstance(payload, dict) else None
        if not isinstance(fuji_payload, dict):
            return None
        rejection = fuji_payload.get("rejection")
        if not isinstance(rejection, dict):
            return None
        if rejection.get("status") != "REJECTED":
            return None
        return rejection

    def _summarize_last_output(
        payload: Dict[str, Any],
        plan_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        chosen = payload.get("chosen") if isinstance(payload, dict) else None
        planner_obj = payload.get("planner") if isinstance(payload, dict) else None
        return {
            "chosen": chosen if isinstance(chosen, dict) else {},
            "plan": plan_payload if isinstance(plan_payload, dict) else {},
            "planner": planner_obj if isinstance(planner_obj, dict) else {},
        }

    if core_decide is None:
        response_extras.setdefault("env_tools", {})
        if isinstance(response_extras["env_tools"], dict):
            response_extras["env_tools"]["kernel_missing"] = True
        _warn("[decide] kernel.decide missing -> skip core call")
    else:
        try:
            raw0 = await call_core_decide(
                core_fn=core_decide,  # type: ignore[arg-type]
                context=context,
                query=query,
                alternatives=input_alts,   # ★ core に渡すのは input_alts
                min_evidence=min_ev,
            )
            raw = raw0 if isinstance(raw0, dict) else {}
        except Exception as e:
            _warn(f"[decide] core error: {e}")
            raw = {}

    if raw and healing_enabled:
        original_task = query
        current_query = query
        current_context = dict(context or {})
        while True:
            rejection = _extract_rejection(raw)
            if not rejection:
                break
            error_code = (rejection.get("error") or {}).get("code") or "unknown"
            feedback_action = (rejection.get("feedback") or {}).get("action")
            decision = self_healing.decide_healing_action(
                error_code=error_code,
                feedback_action=feedback_action,
            )

            attempt_no = healing_state.attempt + 1
            last_output = _summarize_last_output(raw, plan)
            healing_input = self_healing.build_healing_input(
                original_task=original_task,
                last_output=last_output,
                rejection=rejection,
                attempt=attempt_no,
                policy_decision=decision.reason,
            )
            input_signature = self_healing.healing_input_signature(healing_input)
            diff_text = self_healing.diff_summary(prev_healing_input, healing_input)

            stop_reason = self_healing.check_guardrails(
                state=healing_state,
                budget=healing_budget,
                error_code=str(error_code),
                input_signature=input_signature,
            )
            if not decision.allow:
                stop_reason = decision.stop_reason or "policy_blocked"

            budget_snapshot = self_healing.budget_remaining(
                healing_state,
                healing_budget,
            )
            trust_entry = self_healing.build_healing_trust_log_entry(
                request_id=request_id,
                healing_enabled=True,
                attempt=attempt_no,
                prev_error_code=str(error_code),
                chosen_action=decision.action.value,
                budget_snapshot=budget_snapshot,
                diff_summary_text=diff_text,
                linked_trust_log_id=rejection.get("trust_log_id"),
                stop_reason=stop_reason,
            )
            try:
                append_trust_log(trust_entry)
            except Exception as e:
                _warn(f"[self_healing] trust_log skipped: {repr(e)}")

            healing_attempts.append(
                {
                    "attempt": attempt_no,
                    "action": decision.action.value,
                    "error_code": error_code,
                    "stop_reason": stop_reason,
                    "diff_summary": diff_text,
                }
            )
            prev_healing_input = healing_input

            if stop_reason:
                healing_stop_reason = stop_reason
                break

            self_healing.advance_state(
                state=healing_state,
                error_code=str(error_code),
                input_signature=input_signature,
            )

            current_context = dict(context or {})
            current_context["healing"] = {
                "attempt": attempt_no,
                "action": decision.action.value,
                "feedback": rejection.get("feedback"),
                "policy_decision": decision.reason,
            }
            current_query = json.dumps(healing_input, ensure_ascii=False)
            try:
                raw0 = await call_core_decide(
                    core_fn=core_decide,  # type: ignore[arg-type]
                    context=current_context,
                    query=current_query,
                    alternatives=input_alts,
                    min_evidence=min_ev,
                )
                raw = raw0 if isinstance(raw0, dict) else {}
            except Exception as e:
                _warn(f"[self_healing] retry failed: {repr(e)}")
                healing_stop_reason = "retry_execution_failed"
                break

    # =========================================================
    # absorb raw (respect explicit options)
    # =========================================================
    if raw:
        if isinstance(raw.get("evidence"), list):
            for ev0 in raw["evidence"]:
                ev = _norm_evidence_item(ev0)
                if ev:
                    evidence.append(ev)

        if "critique" in raw:
            critique = _normalize_critique_payload(raw.get("critique"))

        debate = raw.get("debate") or debate

        try:
            telos = float(raw.get("telos_score") or telos)
        except Exception:
            pass

        fuji_dict = raw.get("fuji") or fuji_dict

        # core が alternatives/options を返しても、明示 options がある場合は上書きしない
        alts_from_core = raw.get("alternatives") or raw.get("options") or []
        if (not explicit_options) and isinstance(alts_from_core, list) and alts_from_core:
            alternatives = [_norm_alt(a) for a in alts_from_core]

        if isinstance(raw.get("extras"), dict):
            response_extras = _merge_extras_preserving_contract(
                response_extras,
                raw["extras"],
                fast_mode_default=fast_mode,
                context_obj=context,
            )

    if healing_attempts:
        response_extras.setdefault("self_healing", {})
        if isinstance(response_extras["self_healing"], dict):
            response_extras["self_healing"].update(
                {
                    "enabled": True,
                    "attempts": healing_attempts,
                    "stop_reason": healing_stop_reason,
                }
            )

    # =========================================================
    # fallback alternatives (still respects explicit/planner)
    # =========================================================
    alts: List[Dict[str, Any]] = alternatives or [
        _norm_alt({"title": "最小ステップで前進する"}),
        _norm_alt({"title": "情報収集を優先する"}),
        _norm_alt({"title": "今日は休息に充てる"}),
    ]
    alts = _dedupe_alts(alts)

    # =========================================================
    # WorldModel boost (best-effort)
    # =========================================================
    try:
        if world_model is not None and hasattr(world_model, "simulate"):
            boosted: List[Dict[str, Any]] = []
            uid_for_world = (context or {}).get("user_id") or user_id or "anon"
            uid_for_world = str(uid_for_world) if uid_for_world is not None else "anon"

            for d in alts:
                sim = world_model.simulate(user_id=uid_for_world, query=query, chosen=d)  # type: ignore
                if isinstance(sim, dict):
                    d["world"] = sim
                    micro = max(
                        0.0,
                        min(
                            0.03,
                            0.02 * float(sim.get("utility", 0.0)) + 0.01 * float(sim.get("confidence", 0.5)),
                        ),
                    )
                    d["score"] = float(d.get("score", 1.0)) * (1.0 + micro)
                boosted.append(d)
            alts = boosted
    except Exception as e:
        _warn(f"[WorldModelOS] skip: {e}")

    # =========================================================
    # MemoryModel boost (optional)
    # =========================================================
    try:
        response_extras.setdefault("metrics", {})
        if not isinstance(response_extras["metrics"], dict):
            response_extras["metrics"] = {}

        if MEM_VEC is not None and MEM_CLF is not None:
            response_extras["metrics"]["mem_model"] = {
                "applied": True,
                "reason": "loaded",
                "path": _mem_model_path(),
                "classes": getattr(MEM_CLF, "classes_", []).tolist() if hasattr(MEM_CLF, "classes_") else None,
            }
            for d in alts:
                text = (d.get("title") or "") + " " + (d.get("description") or "")
                p_allow = _allow_prob(text)
                base = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", base))
                d["score"] = base * (1.0 + 0.10 * p_allow)
        else:
            response_extras["metrics"]["mem_model"] = {
                "applied": False,
                "reason": "model_not_loaded",
                "path": _mem_model_path(),
            }
    except Exception as e:
        response_extras.setdefault("metrics", {})
        if not isinstance(response_extras["metrics"], dict):
            response_extras["metrics"] = {}
        response_extras["metrics"]["mem_model"] = {"applied": False, "error": str(e), "path": _mem_model_path()}

    # =========================================================
    # chosen (pre-debate)
    # =========================================================
    chosen = raw.get("chosen") if isinstance(raw, dict) else {}
    if not isinstance(chosen, dict) or not chosen:
        try:
            chosen = max(alts, key=lambda d: float((d.get("world") or {}).get("utility", d.get("score", 1.0))))
        except Exception:
            chosen = alts[0] if alts else {}

    # =========================================================
    # DebateOS (best-effort)
    # =========================================================
    debate_result: Dict[str, Any] = {}
    try:
        if debate_core is not None and hasattr(debate_core, "run_debate") and not fast_mode:
            debate_result = debate_core.run_debate(  # type: ignore
                query=query,
                options=alts,
                context={
                    "user_id": user_id,
                    "stakes": (context or {}).get("stakes"),
                    "telos_weights": (context or {}).get("telos_weights"),
                },
            ) or {}
    except Exception as e:
        _warn(f"[DebateOS] skipped: {e}")
        debate_result = {}

    if isinstance(debate_result, dict) and debate_result:
        deb_opts = debate_result.get("options") or []
        if isinstance(deb_opts, list) and deb_opts:
            alts = deb_opts
            debate = deb_opts

        deb_chosen = debate_result.get("chosen")
        if isinstance(deb_chosen, dict) and deb_chosen:
            chosen = deb_chosen

        response_extras.setdefault("debate", {})
        if isinstance(response_extras["debate"], dict):
            try:
                response_extras["debate"].update({"source": debate_result.get("source"), "raw": debate_result.get("raw")})
            except Exception:
                pass

        # heuristic: risk_delta
        try:
            rejected_cnt = 0
            for o in deb_opts:
                if not isinstance(o, dict):
                    continue
                v = str(o.get("verdict") or "").strip()
                if v in ("却下", "reject", "Rejected", "NG"):
                    rejected_cnt += 1
            if rejected_cnt > 0 and deb_opts and isinstance(deb_opts[0], dict):
                deb_opts[0]["risk_delta"] = min(0.20, 0.05 * rejected_cnt)
        except Exception as e:
            _warn(f"[DebateOS] risk_delta heuristic skipped: {e}")

    # =========================================================
    # ISSUE-2: Critique required (post-debate, pre-FUJI)
    # =========================================================
    try:
        critique = _normalize_critique_payload(critique)

        if not critique:
            critique = await _run_critique_best_effort(
                query=query,
                chosen=chosen,
                evidence=evidence if isinstance(evidence, list) else [],
                debate=debate,
                context=context,
                user_id=user_id,
            )

        critique = _ensure_critique_required(
            response_extras=response_extras,
            query=query,
            chosen=chosen,
            critique_obj=critique,
        )
    except Exception:
        critique = _critique_fallback(reason="critique_guard_exception", query=query, chosen=chosen)
        response_extras.setdefault("env_tools", {})
        if isinstance(response_extras["env_tools"], dict):
            response_extras["env_tools"]["critique_degraded"] = True

    # critique がフォールバックならレビュー要求フラグ（extrasに置く）
    try:
        if isinstance(critique, dict) and critique.get("ok") is False:
            response_extras.setdefault("env_tools", {})
            if isinstance(response_extras["env_tools"], dict):
                response_extras["env_tools"]["review_required"] = True
                response_extras["env_tools"]["review_reason"] = "critique_missing_or_failed"
    except Exception:
        pass

    # =========================================================
    # FUJI pre-check (best-effort)
    # =========================================================
    try:
        if fuji_core is not None and hasattr(fuji_core, "validate_action"):
            fuji_pre = fuji_core.validate_action(query, context)  # type: ignore
        elif fuji_core is not None and hasattr(fuji_core, "validate"):
            fuji_pre = fuji_core.validate(query, context)  # type: ignore
        else:
            fuji_pre = {"status": "allow", "reasons": [], "violations": [], "risk": 0.0}
    except Exception as e:
        _warn(f"[fuji] error: {e}")
        fuji_pre = {"status": "allow", "reasons": [], "violations": [], "risk": 0.0}

    status_map = {
        "ok": "allow",
        "allow": "allow",
        "pass": "allow",
        "modify": "modify",
        "block": "rejected",
        "deny": "rejected",
        "rejected": "rejected",
    }
    try:
        if isinstance(fuji_pre, dict):
            fuji_pre["status"] = status_map.get(str(fuji_pre.get("status", "allow")).lower(), "allow")
    except Exception:
        if isinstance(fuji_pre, dict):
            fuji_pre["status"] = "allow"

    fuji_dict = {
        **(fuji_dict if isinstance(fuji_dict, dict) else {}),
        **(fuji_pre if isinstance(fuji_pre, dict) else {}),
    }

    fuji_status = fuji_dict.get("status", "allow")
    try:
        risk_val = float(fuji_dict.get("risk", 0.0))
    except Exception:
        risk_val = 0.0
    reasons_list = fuji_dict.get("reasons", []) or []
    viols = fuji_dict.get("violations", []) or []

    ev_fuji = _norm_evidence_item(
        {
            "source": "internal:fuji",
            "uri": None,
            "snippet": (
                f"[FUJI pre] status={fuji_status}, risk={risk_val}, "
                f"reasons={'; '.join(reasons_list) if reasons_list else '-'}, "
                f"violations={', '.join(viols) if viols else '-'}"
            ),
            "confidence": 0.9 if fuji_status in ("modify", "rejected") else 0.8,
        }
    )
    if ev_fuji:
        evidence.append(ev_fuji)

    # =========================================================
    # ValueCore (best-effort)
    # =========================================================
    try:
        if value_core is not None and hasattr(value_core, "evaluate"):
            vc = value_core.evaluate(query, context or {})  # type: ignore
            values_payload = {
                "scores": getattr(vc, "scores", {}) if vc is not None else {},
                "total": getattr(vc, "total", 0.0) if vc is not None else 0.0,
                "top_factors": getattr(vc, "top_factors", []) if vc is not None else [],
                "rationale": getattr(vc, "rationale", "") if vc is not None else "",
            }
        else:
            values_payload = {"scores": {}, "total": 0.0, "top_factors": [], "rationale": "value_core missing"}
    except Exception as e:
        _warn(f"[value_core] evaluation error: {e}")
        values_payload = {"scores": {}, "total": 0.0, "top_factors": [], "rationale": "evaluation failed"}

    # load EMA
    try:
        vs = _load_valstats()
        value_ema = float(vs.get("ema", 0.5))
    except Exception:
        value_ema = 0.5

    BOOST_MAX = float(os.getenv("VERITAS_VALUE_BOOST_MAX", "0.05"))
    boost = (value_ema - 0.5) * 2.0
    boost = max(-1.0, min(1.0, boost)) * BOOST_MAX

    def _apply_boost(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for d in arr:
            if not isinstance(d, dict):
                continue
            try:
                s = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", s))
                d["score"] = max(0.0, s * (1.0 + boost))
            except Exception:
                pass
            out.append(d)
        return out

    input_alts = _apply_boost(input_alts)
    alts = _apply_boost(alts)

    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))
    try:
        effective_risk = float(fuji_dict.get("risk", 0.0)) * (1.0 - RISK_EMA_WEIGHT * value_ema)
    except Exception:
        effective_risk = 0.0
    effective_risk = max(0.0, min(1.0, effective_risk))

    TELOS_EMA_DELTA = float(os.getenv("VERITAS_TELOS_EMA_DELTA", "0.10"))
    telos_threshold = BASE_TELOS_THRESHOLD - TELOS_EMA_DELTA * (value_ema - 0.5) * 2.0
    telos_threshold = max(TELOS_THRESHOLD_MIN, min(TELOS_THRESHOLD_MAX, telos_threshold))

    # world.utility synthesis (best-effort)
    try:
        v_total = _clip01(values_payload.get("total", 0.5))
        t_val = _clip01(telos)
        r_val = _clip01(effective_risk)

        for d in alts:
            if not isinstance(d, dict):
                continue
            base = _clip01(d.get("score", 0.0))
            util = base
            util *= (0.5 + 0.5 * v_total)
            util *= (1.0 - r_val)
            util *= (0.5 + 0.5 * t_val)
            util = _clip01(util)
            d.setdefault("world", {})
            if isinstance(d["world"], dict):
                d["world"]["utility"] = util

        avg_u = (sum(float((d.get("world") or {}).get("utility", 0.0)) for d in alts) / len(alts)) if alts else 0.0
        response_extras.setdefault("metrics", {})
        if not isinstance(response_extras["metrics"], dict):
            response_extras["metrics"] = {}
        response_extras["metrics"]["avg_world_utility"] = round(float(avg_u), 4)
    except Exception as e:
        _warn(f"[world.utility] skipped: {e}")

    # =========================================================
    # Gate decision
    # =========================================================
    decision_status, rejection_reason = "allow", None
    modifications = fuji_dict.get("modifications") or []

    # merge Debate risk_delta
    try:
        if isinstance(debate, list) and debate:
            delta = float((debate[0] or {}).get("risk_delta", 0.0))
            if delta:
                new_risk = max(0.0, min(1.0, float(fuji_dict.get("risk", 0.0)) + delta))
                fuji_dict["risk"] = new_risk
                effective_risk = max(0.0, min(1.0, new_risk * (1.0 - RISK_EMA_WEIGHT * value_ema)))
    except Exception as e:
        _warn(f"[Debate→FUJI] merge failed: {e}")

    if fuji_dict.get("status") == "modify":
        modifications = fuji_dict.get("modifications") or []
    elif fuji_dict.get("status") == "rejected":
        decision_status = "rejected"
        rejection_reason = "FUJI gate: " + ", ".join(fuji_dict.get("reasons", []) or ["policy_violation"])
        chosen, alts = {}, []
    elif effective_risk >= HIGH_RISK_THRESHOLD and float(telos) < float(telos_threshold):
        decision_status = "rejected"
        rejection_reason = f"FUJI gate: high risk ({effective_risk:.2f}) & low telos (<{telos_threshold:.2f})"
        chosen, alts = {}, []

    # =========================================================
    # Value learning: EMA update (best-effort)
    # =========================================================
    try:
        valstats = _load_valstats()
        alpha = float(valstats.get("alpha", 0.2))
        ema_prev = float(valstats.get("ema", 0.5))
        n_prev = int(valstats.get("n", 0))
        v_val = float(values_payload.get("total", 0.5))

        ema_new = (1.0 - alpha) * ema_prev + alpha * v_val
        hist = valstats.get("history", [])
        if not isinstance(hist, list):
            hist = []
        hist.append({"ts": utc_now_iso_z(), "ema": ema_new, "value": v_val})
        hist = hist[-1000:]
        valstats.update({"ema": ema_new, "n": n_prev + 1, "last": v_val, "history": hist})
        _save_valstats(valstats)

        values_payload["ema"] = round(ema_new, 4)
        value_ema = float(ema_new)
    except Exception as e:
        _warn(f"[value-learning] skip: {e}")

    # =========================================================
    # Metrics
    # =========================================================
    duration_ms = max(1, int((time.time() - started_at) * 1000))

    mem_evi_cnt = 0
    for ev in evidence:
        if isinstance(ev, dict) and str(ev.get("source", "")).startswith("memory"):
            mem_evi_cnt += 1

    response_extras.setdefault("metrics", {})
    if not isinstance(response_extras["metrics"], dict):
        response_extras["metrics"] = {}

    response_extras["metrics"].update(
        {
            "latency_ms": duration_ms,
            "mem_evidence_count": int(mem_evi_cnt),  # backward compat (actual evidence list)
            "memory_evidence_count": int(response_extras["metrics"].get("memory_evidence_count", 0) or 0),  # top_hits count
            "alts_count": int(len(alts)),
            "has_evidence": bool(evidence),
            "value_ema": round(float(value_ema), 4),
            "effective_risk": round(float(effective_risk), 4),
            "telos_threshold": round(float(telos_threshold), 3),
        }
    )

    _ensure_full_contract(response_extras, fast_mode_default=fast_mode, context_obj=context, query_str=query)

    # =========================================================
    # Low-evidence hardening (query hint only)
    # =========================================================

    def _query_is_step1_hint(q: Any) -> bool:
        try:
            qs = (q or "")
            ql = qs.lower()
            return (
                ("step1" in ql)
                or ("step 1" in ql)
                or ("inventory" in ql)
                or ("audit" in ql)
                or ("棚卸" in qs)
                or ("現状" in qs and ("棚卸" in qs or "整理" in qs))
            )
        except Exception:
            return False

    def _has_step1_minimum_evidence(evs: Any) -> bool:
        try:
            if not isinstance(evs, list):
                return False
            has_inv = False
            has_issues = False
            for e in evs:
                if not isinstance(e, dict):
                    continue
                title = str(e.get("title") or "")
                uri = str(e.get("uri") or "")
                snip = str(e.get("snippet") or "")
                kind = str(e.get("kind") or "")

                if (
                    ("inventory" in kind)
                    or ("local:inventory" in title)
                    or ("evidence:inventory" in uri)
                    or ("現状機能（棚卸し）" in snip)
                    or ("棚卸" in snip and "現状" in snip)
                ):
                    has_inv = True

                if (
                    ("known_issues" in kind)
                    or ("local:known_issues" in title)
                    or ("evidence:known_issues" in uri)
                    or ("既知の課題/注意" in snip)
                    or ("既知" in snip and "課題" in snip)
                ):
                    has_issues = True

                if has_inv and has_issues:
                    return True
            return False
        except Exception:
            return False

    try:
        if not isinstance(evidence, list):
            evidence = list(evidence or [])

        step1_intent = False
        if not fast_mode:
            step1_intent = _query_is_step1_hint(query)

        if step1_intent and (not _has_step1_minimum_evidence(evidence)) and (evidence_core is not None):
            fn = getattr(evidence_core, "step1_minimum_evidence", None)
            if callable(fn):
                for ev0 in fn(context):  # type: ignore[misc]
                    evn = _norm_evidence_item(ev0)
                    if evn:
                        evidence.append(evn)
    except Exception:
        pass

    # =========================================================
    # Evidence normalize/dedupe/cap (hardening)
    # =========================================================
    evidence = [ev for ev in (_norm_evidence_item(x) for x in evidence) if ev]  # type: ignore[misc]
    evidence = _dedupe_evidence(evidence)

    EVIDENCE_MAX = int(os.getenv("VERITAS_EVIDENCE_MAX", "50"))
    if len(evidence) > EVIDENCE_MAX:
        evidence = evidence[:EVIDENCE_MAX]

    # =========================================================
    # Response assembly
    # =========================================================
    res: Dict[str, Any] = {
        "ok": True,
        "error": None,
        "request_id": request_id,
        "query": query,
        "chosen": chosen,
        "alternatives": alts,
        "options": list(alts),
        "evidence": evidence,
        "critique": critique,
        "debate": debate,
        "telos_score": float(telos),
        "fuji": fuji_dict,
        "extras": response_extras,
        "gate": {
            "risk": float(effective_risk),
            "telos_score": float(telos),
            "decision_status": decision_status,
            "reason": rejection_reason,
            "modifications": modifications,
        },
        "values": values_payload,
        "persona": load_persona(),
        "version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "decision_status": decision_status,
        "rejection_reason": rejection_reason,
        "memory_citations": response_extras.get("memory_citations", []),
        "memory_used_count": response_extras.get("memory_used_count", 0),
        "plan": plan,
        "planner": response_extras.get("planner", {"steps": [], "raw": None, "source": "fallback"}),
        "trust_log": raw.get("trust_log") if isinstance(raw, dict) else None,
    }

    # =========================================================
    # Audit logs (best-effort)
    # =========================================================
    try:
        audit_entry = {
            "request_id": request_id,
            "created_at": utc_now().isoformat(),
            "context": context,
            "query": query,
            "chosen": chosen,
            "telos_score": float(telos),
            "fuji": fuji_dict if isinstance(fuji_dict, dict) else {},
            "gate_status": (fuji_dict or {}).get("status", "n/a"),
            "gate_risk": float((fuji_dict or {}).get("risk", 0.0)),
            "gate_total": float(values_payload.get("total", 0.0)),
            "plan_steps": len(plan.get("steps", [])) if isinstance(plan, dict) else 0,
            "fast_mode": bool(fast_mode),
            "mem_hits": int((response_extras.get("metrics") or {}).get("mem_hits", 0) or 0),
            "web_hits": int((response_extras.get("metrics") or {}).get("web_hits", 0) or 0),
            "critique_ok": bool((critique or {}).get("ok")) if isinstance(critique, dict) else False,
            "critique_mode": (critique or {}).get("mode") if isinstance(critique, dict) else None,
            "critique_reason": (critique or {}).get("reason") if isinstance(critique, dict) else None,
        }
        audit_entry = redact_payload(audit_entry)
        append_trust_log(audit_entry)
        write_shadow_decide(request_id, body, chosen, float(telos), fuji_dict)
    except Exception as e:
        _warn(f"[audit] log write skipped: {repr(e)}")

    # =========================================================
    # Coerce to DecideResponse (best-effort)
    # =========================================================
    try:
        payload = DecideResponse.model_validate(res).model_dump()
    except Exception as e:
        _warn(f"[model] decide response coerce: {e}")
        payload = res

    # =========================================================
    # Persist decision into MemoryOS
    # =========================================================
    try:
        store2 = _get_memory_store()
        if store2 is not None:
            decision_key = f"decision_{request_id}"
            decision_value = redact_payload(
                {
                    "kind": "decision",
                    "request_id": request_id,
                    "query": query,
                    "chosen": payload.get("chosen"),
                    "gate": payload.get("gate"),
                    "values": payload.get("values"),
                    "extras": payload.get("extras"),
                    "created_at": utc_now_iso_z(),
                }
            )
            _memory_put(
                store2,
                user_id,
                key=decision_key,
                value=decision_value,
            )

            episode_key = f"episode_{time.time_ns()}_{request_id[:8]}"
            episode_value = redact_payload(
                {
                    "kind": "episode",
                    "request_id": request_id,
                    "query": query,
                    "chosen": payload.get("chosen"),
                    "decision_status": payload.get("decision_status"),
                    "rejection_reason": payload.get("rejection_reason"),
                    "created_at": utc_now_iso_z(),
                }
            )
            _memory_put(
                store2,
                user_id,
                key=episode_key,
                value=episode_value,
            )
    except Exception as e:
        extras_tmp = payload.setdefault("extras", {})
        if isinstance(extras_tmp, dict):
            extras_tmp.setdefault("env_tools", {})
            if isinstance(extras_tmp["env_tools"], dict):
                extras_tmp["env_tools"]["memory_decision_save_error"] = repr(e)

    # =========================================================
    # ReasonOS: reflection + meta log (best-effort)
    # =========================================================
    try:
        if reason_core is not None and hasattr(reason_core, "reflect"):
            reflection = reason_core.reflect(  # type: ignore
                {
                    "query": query,
                    "chosen": payload.get("chosen", {}),
                    "gate": payload.get("gate", {}),
                    "values": payload.get("values", {}),
                }
            )
        else:
            reflection = {"next_value_boost": 0.0, "improvement_tips": []}

        try:
            vs_path = Path(VAL_JSON)
            valstats2 = _load_valstats() if vs_path.exists() else {}
            ema2 = float(valstats2.get("ema", 0.5))
            ema2 = max(0.0, min(1.0, ema2 + float(reflection.get("next_value_boost", 0.0) or 0.0)))
            valstats2["ema"] = round(ema2, 4)
            _save_valstats(valstats2)

            Path(META_LOG).parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "created_at": utc_now_iso_z(),
                "request_id": request_id,
                "next_value_boost": float(reflection.get("next_value_boost", 0.0) or 0.0),
                "value_ema": ema2,
                "source": "reason_core",
                "fast_mode": bool(fast_mode),
            }
            with open(META_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e2:
            _warn(f"[ReasonOS] meta_log append skipped: {e2}")

        try:
            llm_reason = None
            if reason_core is not None and hasattr(reason_core, "generate_reason"):
                llm_reason = reason_core.generate_reason(  # type: ignore
                    query=query,
                    planner=payload.get("planner") or payload.get("plan"),
                    values=payload.get("values"),
                    gate=payload.get("gate"),
                    context=context,
                )

            note_text = ""
            if isinstance(llm_reason, dict):
                note_text = llm_reason.get("text") or ""
            elif isinstance(llm_reason, str):
                note_text = llm_reason

            if not note_text:
                tips = reflection.get("improvement_tips") or []
                note_text = " / ".join(tips) if tips else "自動反省メモはありません。"

            payload["reason"] = {
                "note": note_text,
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
                "llm": llm_reason,
            }
        except Exception as e2:
            _warn(f"[ReasonOS] LLM reason failed: {e2}")
            tips = reflection.get("improvement_tips") or []
            payload["reason"] = {
                "note": (" / ".join(tips) if tips else "reflection only."),
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
            }
    except Exception as e:
        _warn(f"[ReasonOS] final fallback failed: {e}")
        payload["reason"] = {"note": "reflection/LLM both failed"}

    # =========================================================
    # Dataset record (best-effort)
    # =========================================================
    try:
        duration_ms_ds = int((payload.get("extras") or {}).get("metrics", {}).get("latency_ms", 0) or duration_ms)
        duration_ms_ds = max(1, duration_ms_ds)

        meta_ds = {
            "session_id": (context or {}).get("user_id") or "anon",
            "request_id": request_id,
            "model": os.getenv("VERITAS_MODEL_NAME", "gpt-5-thinking"),
            "api_version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
            "kernel_version": os.getenv("VERITAS_KERNEL_VERSION", "core-kernel 0.x"),
            "latency_ms": duration_ms_ds,
            "fast_mode": bool(fast_mode),
        }
        eval_meta = {
            "task_type": "decision",
            "policy_tags": ["no_harm", "privacy_ok"],
            "rater": {"type": "ai", "id": "telos-proxy"},
        }
        append_dataset_record(build_dataset_record(req_payload=body, res_payload=payload, meta=meta_ds, eval_meta=eval_meta))
    except Exception as e:
        _warn(f"[dataset] skip: {e}")

    # =========================================================
    # FINALIZE: ensure evidence survives later overwrites
    # =========================================================
    try:
        payload_evidence = payload.get("evidence", None)
        if not isinstance(payload_evidence, list):
            try:
                payload_evidence = list(payload_evidence or [])
            except Exception:
                payload_evidence = []

        if len(payload_evidence) == 0:
            if isinstance(evidence, list) and len(evidence) > 0:
                payload_evidence = list(evidence)
            else:
                payload_evidence = []

        existing = set()
        for ev in payload_evidence:
            if not isinstance(ev, dict):
                continue
            existing.add((ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet")))

        for ev in (web_evidence or []):
            if not isinstance(ev, dict):
                continue
            k = (ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet"))
            if k not in existing:
                payload_evidence.append(ev)
                existing.add(k)

        payload["evidence"] = payload_evidence
    except Exception:
        payload["evidence"] = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []

    # FINALIZE 後: normalize/dedupe/cap
    try:
        payload["evidence"] = _dedupe_evidence(
            [ev for ev in (_norm_evidence_item(x) for x in (payload.get("evidence") or [])) if ev]
        )
    except Exception:
        payload["evidence"] = []

    if isinstance(payload.get("evidence"), list) and len(payload["evidence"]) > EVIDENCE_MAX:
        payload["evidence"] = payload["evidence"][:EVIDENCE_MAX]

    # =========================================================
    # Persist (best-effort)
    # =========================================================
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        Path(DATASET_DIR).mkdir(parents=True, exist_ok=True)

        metrics2 = (payload.get("extras") or {}).get("metrics") or {}
        latency_ms2 = int(metrics2.get("latency_ms", duration_ms))

        evidence_list: List[Dict[str, Any]] = []
        if isinstance(payload.get("evidence"), list):
            evidence_list = [ev for ev in payload["evidence"] if isinstance(ev, dict)]  # type: ignore

        mem_evidence_count2 = 0
        for ev in evidence_list:
            src = str(ev.get("source", "")).lower()
            if src.startswith("memory"):
                mem_evidence_count2 += 1

        meta_payload = payload.get("meta") or {}
        if not isinstance(meta_payload, dict):
            meta_payload = {}

        meta_payload["memory_evidence_count"] = int(metrics2.get("memory_evidence_count", 0) or 0)  # top_hits
        meta_payload["mem_evidence_count"] = int(mem_evidence_count2)  # evidence-based
        meta_payload["mem_hits"] = int(metrics2.get("mem_hits", 0) or 0)
        meta_payload["web_hits"] = int(metrics2.get("web_hits", 0) or 0)
        meta_payload["fast_mode"] = bool((payload.get("extras") or {}).get("fast_mode", fast_mode))
        payload["meta"] = meta_payload

        fuji_full = payload.get("fuji") or {}
        world_snapshot = (context or {}).get("world")

        persist = redact_payload({
            "request_id": request_id,
            "ts": utc_now_iso_z(timespec="seconds"),
            "query": query,
            "chosen": payload.get("chosen"),
            "decision_status": payload.get("decision_status") or "unknown",
            "telos_score": float(payload.get("telos_score", 0.0)),
            "gate_risk": float(((payload.get("gate") or {}) if isinstance(payload.get("gate"), dict) else {}).get("risk", 0.0)),
            "fuji_status": fuji_full.get("status") if isinstance(fuji_full, dict) else None,
            "fuji": fuji_full,
            "latency_ms": latency_ms2,
            "evidence": evidence_list[-5:] if evidence_list else [],
            "memory_evidence_count": int(meta_payload.get("memory_evidence_count", 0) or 0),
            "mem_evidence_count": int(meta_payload.get("mem_evidence_count", 0) or 0),
            "context": context,
            "world": world_snapshot,
            "fast_mode": bool((payload.get("extras") or {}).get("fast_mode", fast_mode)),
            "mem_hits": int(metrics2.get("mem_hits", 0) or 0),
            "web_hits": int(metrics2.get("web_hits", 0) or 0),
            "critique_ok": bool((critique or {}).get("ok")) if isinstance(critique, dict) else False,
            "critique_mode": (critique or {}).get("mode") if isinstance(critique, dict) else None,
            "critique_reason": (critique or {}).get("reason") if isinstance(critique, dict) else None,
        })

        stamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fname = f"decide_{stamp}.json"
        (Path(LOG_DIR) / fname).write_text(json.dumps(persist, ensure_ascii=False, indent=2), encoding="utf-8")
        (Path(DATASET_DIR) / fname).write_text(json.dumps(persist, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        _warn(f"[persist] decide record skipped: {e}")

    # =========================================================
    # WorldState update (best-effort)
    # =========================================================
    try:
        if world_model is not None and hasattr(world_model, "update_from_decision"):
            uid_world = (context or {}).get("user_id") or user_id or "anon"
            uid_world = str(uid_world) if uid_world is not None else "anon"

            extras_w = payload.get("extras") or {}
            planner_obj = extras_w.get("planner") if isinstance(extras_w, dict) else None
            latency_ms3 = (extras_w.get("metrics") or {}).get("latency_ms") if isinstance(extras_w, dict) else None

            world_model.update_from_decision(  # type: ignore
                user_id=uid_world,
                query=payload.get("query") or query,
                chosen=payload.get("chosen") or {},
                gate=payload.get("gate") or {},
                values=payload.get("values") or {},
                planner=planner_obj if isinstance(planner_obj, dict) else None,
                latency_ms=int(latency_ms3) if isinstance(latency_ms3, (int, float)) else None,
            )
            _warn(f"[WorldModel] state updated for {uid_world}")
    except Exception as e:
        _warn(f"[WorldModel] update_from_decision skipped: {e}")

    # AGI hint (best-effort)
    try:
        if world_model is not None and hasattr(world_model, "next_hint_for_veritas_agi"):
            agi_info = world_model.next_hint_for_veritas_agi()  # type: ignore
            extras2 = payload.setdefault("extras", {})
            if isinstance(extras2, dict):
                extras2["veritas_agi"] = agi_info
    except Exception as e:
        _warn(f"[WorldModel] next_hint_for_veritas_agi skipped: {e}")

    return payload
