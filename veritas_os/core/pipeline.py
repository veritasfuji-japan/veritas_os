# veritas_os/core/pipeline.py
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
VERITAS Decision Pipeline – Orchestrator (core/pipeline.py)

This module is the *single entry-point* for the /v1/decide endpoint.
``run_decide_pipeline(req, request)`` orchestrates the full decision flow
by delegating to responsibility-separated stage modules:

  pipeline_inputs   – input normalisation
  pipeline_execute  – kernel.decide + self-healing
  pipeline_policy   – FUJI / gate / ValueCore
  pipeline_response – response assembly & evidence finalisation
  pipeline_persist  – audit, disk persist, memory, world-state, replay
  pipeline_replay   – deterministic replay & diff
  pipeline_types    – PipelineContext dataclass + constants

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

import inspect
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
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
from . import self_healing  # noqa: F401 - tests monkeypatch pipeline.self_healing

# ---- pipeline サブモジュール（分割済み） ----
from .pipeline_helpers import (
    _as_str,
    _norm_severity,
    _now_iso,
    _to_bool_local,
    _set_int_metric,
    _set_bool_metric,
    _lazy_import,
    _extract_rejection,
    _summarize_last_output,
    _query_is_step1_hint,
    _has_step1_minimum_evidence,
    _apply_value_boost,
)
from .pipeline_critique import (
    _default_findings,
    _pad_findings,
    _critique_fallback,
    _list_to_findings,
    _normalize_critique_payload,
    _ensure_critique_required,
    _chosen_to_option,
    _run_critique_best_effort,
)
from .pipeline_evidence import (
    _norm_evidence_item,
    _dedupe_evidence,
    _norm_evidence_item_simple,
    _evidencepy_to_pipeline_item,
)
from .pipeline_memory_adapter import (
    _get_memory_store as _get_memory_store_impl,
    _call_with_accepted_kwargs,
    _memory_has,
    _memory_search,
    _memory_put,
    _memory_add_usage,
    _flatten_memory_hits,
)
from .pipeline_web_adapter import (
    _normalize_web_payload,
    _extract_web_results,
)
from .pipeline_contracts import (
    _ensure_full_contract,
    _ensure_metrics_contract,
    _deep_merge_dict,
    _merge_extras_preserving_contract,
)

# ---- Stage modules (responsibility-separated) ----
from .pipeline_types import (  # noqa: F401 – re-exported for backward compat
    PipelineContext,
    MIN_MEMORY_SIMILARITY,
    DEFAULT_CONFIDENCE,
    DOC_MIN_CONFIDENCE,
    TELOS_THRESHOLD_MIN,
    TELOS_THRESHOLD_MAX,
    HIGH_RISK_THRESHOLD,
    BASE_TELOS_THRESHOLD,
)
from .pipeline_inputs import normalize_pipeline_inputs
from .pipeline_execute import stage_core_execute
from .pipeline_policy import (
    stage_fuji_precheck,
    stage_value_core,
    stage_gate_decision,
)
from .pipeline_response import (
    assemble_response,
    coerce_to_decide_response,
    finalize_evidence,
)
from .pipeline_persist import (
    persist_audit_log,
    persist_to_memory,
    persist_reason_and_reflection,
    persist_dataset_record,
    persist_decision_to_disk,
    persist_world_state,
    build_replay_snapshot,
)
from .pipeline_retrieval import (
    stage_memory_retrieval,
    stage_web_search_async,
)
from .pipeline_decide_stages import (
    stage_normalize_options,
    stage_absorb_raw_results,
    stage_fallback_alternatives,
    stage_model_boost,
    stage_debate as stage_debate_fn,
    stage_critique_async,
    stage_value_learning_ema,
    stage_compute_metrics,
    stage_evidence_hardening,
)
from .pipeline_replay import (
    _safe_filename_id,  # noqa: F401 – backward compat
    _sanitize_for_diff,  # noqa: F401 – backward compat
    _build_replay_diff,  # noqa: F401 – backward compat
    _load_persisted_decision as _load_persisted_decision_impl,
    _ReplayRequest,  # noqa: F401 – backward compat
    replay_decision as _replay_decision_impl,
)

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    _HAS_ATOMIC_IO = True
except (ImportError, ModuleNotFoundError):
    _atomic_write_json = None  # type: ignore
    _HAS_ATOMIC_IO = False


try:
    from fastapi import Request
except (ImportError, ModuleNotFoundError):  # tests may import pipeline without fastapi installed
    Request = Any  # type: ignore


# =========================================================
# repo root / time helpers
# =========================================================

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os

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
    """Convert value to bool (for env vars, config values, etc.).

    Delegates to ``_to_bool_local`` from pipeline_helpers to eliminate
    duplication while keeping the public name for backward compatibility.
    """
    return _to_bool_local(v)


def _warn(msg: str) -> None:
    """警告メッセージを出力（環境変数で抑制可能）。メッセージの接頭辞に応じてログレベルを自動選択する。

    NOTE: This is kept as a standalone function (not delegating to
    pipeline_helpers._warn) because tests capture logs from the
    ``veritas_os.core.pipeline`` logger name and monkeypatch this
    function directly.  Sub-modules use the shared implementation
    from ``pipeline_helpers._warn`` instead.
    """
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
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    veritas_core = None  # type: ignore
    _warn(f"[ERROR][pipeline] kernel import failed (REQUIRED): {repr(e)}")

# ---- fuji (REQUIRED) ----
try:
    from . import fuji as fuji_core  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    fuji_core = None  # type: ignore
    _warn(f"[ERROR][pipeline] fuji import failed (REQUIRED): {repr(e)}")

# ---- memory (RECOMMENDED) ----
try:
    from . import memory as mem  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    mem = None  # type: ignore
    _warn(f"[WARN][pipeline] memory import failed (RECOMMENDED): {repr(e)}")

# ---- value_core (RECOMMENDED) ----
try:
    from . import value_core  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    value_core = None  # type: ignore
    _warn(f"[WARN][pipeline] value_core import failed (RECOMMENDED): {repr(e)}")

# ---- world model (RECOMMENDED) ----
try:
    from . import world as world_model  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    world_model = None  # type: ignore
    _warn(f"[WARN][pipeline] world import failed (RECOMMENDED): {repr(e)}")

# ---- reason (OPTIONAL) ----
try:
    from . import reason as reason_core  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    reason_core = None  # type: ignore
    _warn(f"[INFO][pipeline] reason import failed (OPTIONAL): {repr(e)}")

# ---- debate (RECOMMENDED) ----
try:
    from . import debate as debate_core  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    debate_core = None  # type: ignore
    _warn(f"[WARN][pipeline] debate import failed (RECOMMENDED): {repr(e)}")


# =========================================================
# Safe imports (API schemas / persona)
# =========================================================

try:
    from veritas_os.api.schemas import DecideRequest, DecideResponse  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    DecideRequest = Any  # type: ignore
    DecideResponse = Any  # type: ignore
    _warn(f"[WARN][pipeline] api.schemas import failed: {repr(e)}")

try:
    from veritas_os.api.evolver import load_persona  # type: ignore
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    def load_persona() -> dict:  # type: ignore
        return {"name": "fallback", "mode": "minimal"}

try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii  # type: ignore
    _HAS_SANITIZE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
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
        try:
            return o.model_dump(exclude_none=True)  # type: ignore
        except (TypeError, ValueError, RuntimeError):
            logger.debug("_to_dict: model_dump() failed for %r", type(o).__name__, exc_info=True)
    if hasattr(o, "dict"):
        try:
            return o.dict()  # type: ignore
        except (TypeError, ValueError, RuntimeError):
            logger.debug("_to_dict: dict() failed for %r", type(o).__name__, exc_info=True)
    try:
        if hasattr(o, "__dict__"):
            raw = o.__dict__
            if isinstance(raw, dict):
                # Filter out values that reference the original object to
                # prevent circular references from breaking downstream
                # JSON serialization.
                return {
                    k: v for k, v in raw.items()
                    if v is not o
                }
            # __dict__ returned a non-dict (e.g. int) – fall through
    except (TypeError, ValueError, AttributeError):
        logger.debug("_to_dict: __dict__ fallback failed for %r", type(o).__name__, exc_info=True)
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
    except Exception:  # subsystem resilience: request objects may raise arbitrary errors
        logger.debug("_get_request_params: query_params extraction failed", exc_info=True)
    try:
        pm = getattr(request, "params", None)
        if pm is not None:
            out.update(dict(pm))
    except Exception:  # subsystem resilience: request objects may raise arbitrary errors
        logger.debug("_get_request_params: params extraction failed", exc_info=True)
    return out


# _ensure_metrics_contract -> pipeline_contracts.py に移動済み（上部 import）


def _get_memory_store() -> Optional[Any]:
    """pipeline.mem を参照するラッパー（テストが monkeypatch で pipeline.mem をパッチ可能にする）。"""
    if mem is None:
        return None
    return _get_memory_store_impl(mem=mem)


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
    # ★ 制御文字・null バイト・Unicode制御文字（bidiオーバーライド等）を除去し、
    #   長さを制限（downstream 安全性）
    _id = d.get("id")
    if _id is None or (isinstance(_id, str) and _id.strip() == ""):
        d["id"] = uuid4().hex
    else:
        _id_str = str(_id)
        # ASCII control chars + DEL
        _id_str = re.sub(r"[\x00-\x1f\x7f]", "", _id_str)
        # Unicode categories: Cc (control), Cf (format/bidi overrides),
        # Cs (surrogates), Co (private use), Zl (line separator),
        # Zp (paragraph separator) – none belong in an ID string.
        _UNSAFE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}
        _id_str = "".join(
            ch for ch in _id_str
            if unicodedata.category(ch) not in _UNSAFE_CATEGORIES
        )
        if len(_id_str) > 256:
            _id_str = _id_str[:256]
        d["id"] = _id_str if _id_str.strip() else uuid4().hex

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
    except (ImportError, AttributeError, OSError) as e:
        _warn(f"[WARN][pipeline] logging.paths import failed -> fallback: {repr(e)}")
        LOG_DIR = (Path(env_log).resolve() if env_log else (REPO_ROOT / "logs").resolve())
        DATASET_DIR = (Path(env_ds).resolve() if env_ds else (REPO_ROOT / "dataset").resolve())
        VAL_JSON = (LOG_DIR / "value_ema.json").resolve()
        META_LOG = (LOG_DIR / "meta.log").resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG


LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG = _safe_paths()
REPLAY_REPORT_DIR = (REPO_ROOT / "audit" / "replay_reports").resolve()
_EVIDENCE_MAX_UPPER = 10000  # Upper bound for EVIDENCE_MAX to prevent unreasonable memory usage
try:
    EVIDENCE_MAX = int(os.getenv("VERITAS_EVIDENCE_MAX", "50"))
except (ValueError, TypeError):
    logger.warning("VERITAS_EVIDENCE_MAX=%r is not a valid integer, using default 50", os.getenv("VERITAS_EVIDENCE_MAX"))
    EVIDENCE_MAX = 50
if not (1 <= EVIDENCE_MAX <= _EVIDENCE_MAX_UPPER):
    logger.warning("VERITAS_EVIDENCE_MAX=%d out of bounds [1,%d], using default 50", EVIDENCE_MAX, _EVIDENCE_MAX_UPPER)
    EVIDENCE_MAX = 50

# ★ Replay functions moved to pipeline_replay.py.
# _safe_filename_id, _sanitize_for_diff, _build_replay_diff,
# _load_persisted_decision, _ReplayRequest are imported above for backward compat.
# _SAFE_FILENAME_RE kept here only for direct-access backward compat.
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _load_persisted_decision(decision_id: str) -> Optional[Dict[str, Any]]:
    """Backward-compat wrapper that passes LOG_DIR automatically."""
    return _load_persisted_decision_impl(decision_id, LOG_DIR=LOG_DIR)


async def replay_decision(
    decision_id: str,
    *,
    mock_external_apis: bool = True,
) -> Dict[str, Any]:
    """Replay a persisted decision deterministically and generate an audit diff report.

    Delegates to ``pipeline_replay.replay_decision`` while injecting
    module-level dependencies.  This wrapper keeps backward-compat:
    tests can monkeypatch ``pipeline._load_persisted_decision``,
    ``pipeline.run_decide_pipeline``, ``pipeline.DecideRequest``,
    etc. and the changes are respected because the references are
    captured at call time, not import time.
    """
    return await _replay_decision_impl(
        decision_id,
        mock_external_apis=mock_external_apis,
        run_decide_pipeline_fn=run_decide_pipeline,
        DecideRequest=DecideRequest,
        LOG_DIR=LOG_DIR,
        REPLAY_REPORT_DIR=REPLAY_REPORT_DIR,
        _HAS_ATOMIC_IO=_HAS_ATOMIC_IO,
        _atomic_write_json=_atomic_write_json,
        _load_decision_fn=_load_persisted_decision,
    )


# =========================================================
# Safe dataset writer (optional)
# =========================================================

try:
    from veritas_os.logging.dataset_writer import build_dataset_record, append_dataset_record  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
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
except (ImportError, ModuleNotFoundError):  # pragma: no cover
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
    except Exception:  # subsystem resilience: intentionally broad
        logger.debug("_mem_model_path: import/attr lookup failed", exc_info=True)
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
            except Exception:  # subsystem resilience: intentionally broad
                logger.debug("predict_gate_label failed", exc_info=True)
                return {"allow": 0.5}

except Exception:  # subsystem resilience: intentionally broad
    logger.debug("memory_model import failed", exc_info=True)


def _allow_prob(text: str) -> float:
    d = predict_gate_label(text)
    try:
        return float(d.get("allow", 0.0))
    except (ValueError, TypeError, AttributeError):
        return 0.0


def _load_valstats() -> Dict[str, Any]:
    try:
        p = Path(VAL_JSON)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                return obj
    except (OSError, json.JSONDecodeError, ValueError):
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
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
    except OSError as e:
        logger.warning("_save_valstats failed: %s", e)


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


def _dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Prefer kernel helper if present
    try:
        if veritas_core is not None and hasattr(veritas_core, "_dedupe_alts"):
            result = veritas_core._dedupe_alts(alts)  # type: ignore
            if isinstance(result, list):
                return result
            logger.debug("_dedupe_alts: kernel helper returned %s, expected list", type(result).__name__)
    except Exception:  # subsystem resilience: kernel._dedupe_alts may raise arbitrary errors
        logger.debug("_dedupe_alts: kernel helper failed, using fallback", exc_info=True)
    return _dedupe_alts_fallback(alts)


async def call_core_decide(
    core_fn: Callable,
    context: Optional[Dict[str, Any]],
    query: str,
    alternatives: Optional[List[Dict[str, Any]]],
    min_evidence: Optional[int] = None,
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

    def _params(fn) -> Set[str]:
        try:
            return set(inspect.signature(fn).parameters.keys())
        except Exception:  # subsystem resilience: intentionally broad
            logger.debug("call_core_decide: signature inspection failed for %r", fn)
            return set()

    p = _params(core_fn)

    # ---- Try A: ctx/options style ----
    try:
        if ("ctx" in p) or ("options" in p):
            res = core_fn(ctx=ctx, options=opts, min_evidence=min_evidence, query=query)
            return await res if _is_awaitable(res) else res
    except TypeError:
        # Re-raise if TypeError originated inside core_fn (tb depth > 1),
        # only suppress genuine signature-mismatch errors.
        import sys as _sys
        _tb = _sys.exc_info()[2]
        if _tb is not None and _tb.tb_next is not None:
            raise
        del _tb

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
        import sys as _sys
        _tb = _sys.exc_info()[2]
        if _tb is not None and _tb.tb_next is not None:
            raise
        del _tb

    # ---- Try C: positional (last resort) ----
    try:
        res = core_fn(ctx, query, opts, min_evidence)
        return await res if _is_awaitable(res) else res
    except TypeError as e:
        raise TypeError(
            f"call_core_decide: all calling conventions failed for {core_fn!r}. "
            f"Last error: {e}"
        ) from e


# =========================================================
# Memory adapter -> pipeline_memory_adapter.py に移動済み
# (_get_memory_store, _call_with_accepted_kwargs, _memory_has,
#  _memory_search, _memory_put, _memory_add_usage)
# =========================================================


# =========================================================
# Optional: WebSearch adapter (do not crash import)
# =========================================================

_tool_web_search = None
try:
    from veritas_os.tools.web_search import web_search as _tool_web_search  # type: ignore
except (ImportError, ModuleNotFoundError):
    # optional dependency / env missing in CI or local
    _tool_web_search = None


async def _safe_web_search(query: str, *, max_results: int = 5) -> Optional[dict]:
    """Returns web_search result dict or None (never raises).
    Supports both sync/async web_search (tests often monkeypatch async).

    Resolution order:
      1. module-level ``web_search`` (set by monkeypatch in tests)
      2. ``_tool_web_search`` (imported from tools.web_search)
    """
    import sys
    _this = sys.modules[__name__]
    fn = getattr(_this, "web_search", None)
    if not callable(fn):
        fn = getattr(_this, "_tool_web_search", None)
    if not callable(fn):
        return None

    try:
        ws = fn(query, max_results=max_results)  # type: ignore[misc]
        if inspect.isawaitable(ws):
            ws = await ws
        return ws if isinstance(ws, dict) else None
    except Exception:  # subsystem resilience: intentionally broad
        logger.debug("_safe_web_search failed for query=%r", query, exc_info=True)
        return None


# _normalize_web_payload -> pipeline_web_adapter.py に移動済み

# =========================================================
# evidence.py -> pipeline item
# =========================================================
try:
    from veritas_os.core import evidence as evidence_core  # type: ignore
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    evidence_core = None  # type: ignore
    _warn(f"[WARN][pipeline] evidence import failed (OPTIONAL): {repr(e)}")

# _norm_evidence_item_simple, _evidencepy_to_pipeline_item ->
# pipeline_evidence.py に移動済み（上部 import で re-export 済み）


# =========================================================
# main pipeline (FULL / hardened) - Orchestrator
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

    Stage modules:
      1. pipeline_inputs          – input normalisation & PlannerOS
      2. pipeline_retrieval       – MemoryOS retrieval + WebSearch
      3. pipeline_decide_stages   – options normalization
      4. pipeline_execute         – kernel.decide + self-healing
      4b-4d. pipeline_decide_stages – absorb raw / fallback / boost
      5-5b. pipeline_decide_stages  – debate / critique
      6. pipeline_policy          – FUJI / ValueCore / gate
      6b-6d. pipeline_decide_stages – EMA / metrics / evidence hardening
      7. pipeline_response        – response assembly & evidence finalisation
      8. pipeline_persist         – audit, disk, memory, world-state, replay
    """

    # Required modules check
    _check_required_modules()

    # =================================================================
    # Stage 1: Input normalization  (-> pipeline_inputs)
    # =================================================================
    ctx = normalize_pipeline_inputs(
        req,
        request,
        _get_request_params=_get_request_params,
        _to_dict_fn=_to_dict,
    )

    # =================================================================
    # Stage 2: MemoryOS retrieval  (-> pipeline_retrieval)
    # =================================================================
    stage_memory_retrieval(
        ctx,
        _get_memory_store=_get_memory_store,
        _memory_search=_memory_search,
        _memory_put=_memory_put,
        _memory_add_usage=_memory_add_usage,
        _flatten_memory_hits=_flatten_memory_hits,
        _warn=_warn,
        utc_now_iso_z=utc_now_iso_z,
    )

    # =================================================================
    # Stage 2b: WebSearch  (-> pipeline_retrieval)
    # =================================================================
    await stage_web_search_async(
        ctx,
        _safe_web_search=_safe_web_search,
        _normalize_web_payload=_normalize_web_payload,
        _extract_web_results=_extract_web_results,
        _to_bool=_to_bool,
        _get_request_params=_get_request_params,
        _warn=_warn,
        request=request,
    )

    # =================================================================
    # Stage 3: Options normalization  (-> pipeline_decide_stages)
    # =================================================================
    stage_normalize_options(ctx, _norm_alt=_norm_alt)

    # =================================================================
    # Stage 4: Core decision + self-healing  (-> pipeline_execute)
    # =================================================================
    await stage_core_execute(
        ctx,
        call_core_decide_fn=call_core_decide,
        append_trust_log_fn=append_trust_log,
        veritas_core=veritas_core,
    )

    # =================================================================
    # Stage 4b: Absorb raw results  (-> pipeline_decide_stages)
    # =================================================================
    stage_absorb_raw_results(
        ctx,
        _norm_alt=_norm_alt,
        _normalize_critique_payload=_normalize_critique_payload,
        _merge_extras_preserving_contract=_merge_extras_preserving_contract,
    )

    # =================================================================
    # Stage 4c: Fallback alternatives  (-> pipeline_decide_stages)
    # =================================================================
    stage_fallback_alternatives(ctx, _norm_alt=_norm_alt, _dedupe_alts=_dedupe_alts)

    # =================================================================
    # Stage 4d: WorldModel + MemoryModel boost  (-> pipeline_decide_stages)
    # =================================================================
    stage_model_boost(
        ctx,
        world_model=world_model,
        MEM_VEC=MEM_VEC,
        MEM_CLF=MEM_CLF,
        _allow_prob=_allow_prob,
        _mem_model_path=_mem_model_path,
        _warn=_warn,
    )

    # =================================================================
    # Stage 5: DebateOS  (-> pipeline_decide_stages)
    # =================================================================
    stage_debate_fn(ctx, debate_core=debate_core, _warn=_warn)

    # =================================================================
    # Stage 5b: Critique  (-> pipeline_decide_stages)
    # =================================================================
    await stage_critique_async(
        ctx,
        _normalize_critique_payload=_normalize_critique_payload,
        _run_critique_best_effort=_run_critique_best_effort,
        _ensure_critique_required=_ensure_critique_required,
        _critique_fallback=_critique_fallback,
    )

    # =================================================================
    # Stage 6: Policy (FUJI + ValueCore + Gate)  (-> pipeline_policy)
    # =================================================================
    stage_fuji_precheck(ctx)
    stage_value_core(ctx, _load_valstats=_load_valstats, _clip01=_clip01)
    stage_gate_decision(ctx)

    # =================================================================
    # Stage 6b: Value learning EMA  (-> pipeline_decide_stages)
    # =================================================================
    stage_value_learning_ema(
        ctx,
        _load_valstats=_load_valstats,
        _save_valstats=_save_valstats,
        _warn=_warn,
        utc_now_iso_z=utc_now_iso_z,
    )

    # =================================================================
    # Stage 6c: Metrics  (-> pipeline_decide_stages)
    # =================================================================
    stage_compute_metrics(ctx, _ensure_full_contract=_ensure_full_contract)

    # =================================================================
    # Stage 6d: Low-evidence hardening  (-> pipeline_decide_stages)
    # =================================================================
    stage_evidence_hardening(
        ctx,
        evidence_core=evidence_core,
        _query_is_step1_hint=_query_is_step1_hint,
        _has_step1_minimum_evidence=_has_step1_minimum_evidence,
    )

    # =================================================================
    # Stage 7: Response assembly  (-> pipeline_response)
    # =================================================================
    plan = ctx.plan
    res = assemble_response(ctx, load_persona_fn=load_persona, plan=plan)
    payload = coerce_to_decide_response(res, DecideResponse=DecideResponse)

    # =================================================================
    # Stage 8: Persist / telemetry  (-> pipeline_persist)
    # =================================================================
    persist_audit_log(ctx, append_trust_log_fn=append_trust_log, write_shadow_decide_fn=write_shadow_decide)

    persist_to_memory(ctx, payload, _get_memory_store=_get_memory_store, _memory_put=_memory_put)

    persist_reason_and_reflection(
        ctx, payload,
        VAL_JSON=VAL_JSON, META_LOG=META_LOG,
        _load_valstats=_load_valstats, _save_valstats=_save_valstats,
    )

    # FINALIZE evidence
    finalize_evidence(payload, web_evidence=ctx.web_evidence, evidence_max=EVIDENCE_MAX)

    duration_ms = max(1, int((time.time() - ctx.started_at) * 1000))
    persist_decision_to_disk(
        ctx, payload, duration_ms=duration_ms,
        LOG_DIR=LOG_DIR, DATASET_DIR=DATASET_DIR,
        _HAS_ATOMIC_IO=_HAS_ATOMIC_IO, _atomic_write_json=_atomic_write_json,
    )

    persist_world_state(ctx, payload)

    persist_dataset_record(
        ctx, payload, duration_ms=duration_ms,
        build_dataset_record_fn=build_dataset_record,
        append_dataset_record_fn=append_dataset_record,
    )

    # =================================================================
    # Stage 8b: Replay snapshot
    # =================================================================
    should_run_web = getattr(ctx, "_should_run_web", False)
    build_replay_snapshot(ctx, payload, should_run_web=should_run_web)

    return payload
