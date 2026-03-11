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

import asyncio
import inspect
import json
import logging
import os
import random  # nosec B311 - deterministic test seeding only
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
        return o.model_dump(exclude_none=True)  # type: ignore
    if hasattr(o, "dict"):
        return o.dict()  # type: ignore
    if hasattr(o, "__dict__"):
        try:
            return dict(o.__dict__)
        except (TypeError, ValueError):
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
    except Exception:  # subsystem resilience: request objects may raise arbitrary errors
        pass
    try:
        pm = getattr(request, "params", None)
        if pm is not None:
            out.update(dict(pm))
    except Exception:  # subsystem resilience: request objects may raise arbitrary errors
        pass
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
    except (ImportError, AttributeError, OSError) as e:
        _warn(f"[WARN][pipeline] logging.paths import failed -> fallback: {repr(e)}")
        LOG_DIR = (Path(env_log).resolve() if env_log else (REPO_ROOT / "logs").resolve())
        DATASET_DIR = (Path(env_ds).resolve() if env_ds else (REPO_ROOT / "dataset").resolve())
        VAL_JSON = (LOG_DIR / "value_ema.json").resolve()
        META_LOG = (LOG_DIR / "meta.log").resolve()
        return LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG


LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG = _safe_paths()
REPLAY_REPORT_DIR = (REPO_ROOT / "audit" / "replay_reports").resolve()

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

    This wrapper keeps backward-compat: tests can monkeypatch
    ``pipeline._load_persisted_decision``, ``pipeline.run_decide_pipeline``,
    etc. and the changes are respected.
    """
    started_at = time.time()
    snapshot = _load_persisted_decision(decision_id)
    if snapshot is None:
        return {
            "match": False,
            "diff": {"error": "decision_not_found", "decision_id": decision_id},
            "replay_time_ms": max(1, int((time.time() - started_at) * 1000)),
        }

    replay_meta = snapshot.get("deterministic_replay") or {}
    req_body = replay_meta.get("request_body") or {}
    if not isinstance(req_body, dict):
        req_body = {}

    req_body.setdefault("query", snapshot.get("query") or "")
    ctx = req_body.setdefault("context", {})
    if not isinstance(ctx, dict):
        ctx = {}
        req_body["context"] = ctx

    req_body["request_id"] = str(snapshot.get("request_id") or decision_id)
    req_body["seed"] = replay_meta.get("seed", req_body.get("seed", 0))
    req_body["temperature"] = replay_meta.get(
        "temperature", req_body.get("temperature", 0)
    )
    ctx["_replay_mode"] = True
    ctx["_mock_external_apis"] = bool(mock_external_apis)

    if hasattr(DecideRequest, "model_validate"):
        replay_req = DecideRequest.model_validate(req_body)
    else:
        replay_req = req_body

    replay_output = await run_decide_pipeline(replay_req, _ReplayRequest())
    original_output = replay_meta.get("final_output") or {}
    if not isinstance(original_output, dict):
        original_output = {}
    diff = _build_replay_diff(original_output, replay_output)
    match = not bool(diff.get("changed"))

    report = {
        "decision_id": str(snapshot.get("request_id") or decision_id),
        "match": match,
        "diff": diff,
        "replay_time_ms": max(1, int((time.time() - started_at) * 1000)),
        "created_at": utc_now_iso_z(),
    }

    try:
        REPLAY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = _safe_filename_id(report["decision_id"])
        report_path = REPLAY_REPORT_DIR / f"replay_{safe_id}_{int(time.time() * 1000)}.json"
        if _HAS_ATOMIC_IO and _atomic_write_json is not None:
            _atomic_write_json(report_path, report, indent=2)
        else:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
    except (ValueError, TypeError) as e:
        report.setdefault("diff", {})
        report["diff"]["report_save_error"] = repr(e)

    return {
        "match": report["match"],
        "diff": report["diff"],
        "replay_time_ms": report["replay_time_ms"],
    }


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
            except Exception:  # subsystem resilience: intentionally broad
                return {"allow": 0.5}

except Exception:  # subsystem resilience: intentionally broad
    pass


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
                os.fsync(f.fileno())
    except OSError as e:
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
    except Exception:  # subsystem resilience: kernel._dedupe_alts may raise arbitrary errors
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
        except Exception:  # subsystem resilience: intentionally broad
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
    except Exception:  # subsystem resilience: intentionally broad
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
      1. pipeline_inputs     - input normalisation & PlannerOS
      2. (inline)            - MemoryOS retrieval + WebSearch
      3. (inline)            - options normalization
      4. pipeline_execute    - kernel.decide + self-healing
      5. (inline)            - absorb raw / debate / critique
      6. pipeline_policy     - FUJI / ValueCore / gate
      7. pipeline_response   - response assembly & evidence finalisation
      8. pipeline_persist    - audit, disk, memory, world-state, replay
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
    body = ctx.body
    context = ctx.context
    query = ctx.query
    user_id = ctx.user_id
    fast_mode = ctx.fast_mode
    replay_mode = ctx.replay_mode
    mock_external_apis = ctx.mock_external_apis
    request_id = ctx.request_id
    seed = ctx.seed
    min_ev = ctx.min_ev
    is_veritas_query = ctx.is_veritas_query
    plan = ctx.plan
    response_extras = ctx.response_extras
    evidence = ctx.evidence
    started_at = ctx.started_at

    qlower = query.lower()

    # =================================================================
    # Stage 2: MemoryOS retrieval  (best-effort)
    # =================================================================
    retrieval_stage_started_at = time.time()
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
                except Exception:  # subsystem resilience: intentionally broad
                    doc_hits_raw = None

            flat_hits: List[Dict[str, Any]] = []
            flat_hits.extend(_flatten_memory_hits(mem_hits_raw))
            flat_hits.extend(_flatten_memory_hits(doc_hits_raw, default_kind="doc"))

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
            except (KeyError, TypeError, AttributeError):
                pass

        except Exception as e:  # subsystem resilience: intentionally broad
            _warn(f"[AGI-Retrieval] memory retrieval error: {repr(e)}")
            response_extras.setdefault("env_tools", {})
            response_extras["env_tools"]["memory_error"] = repr(e)

    response_extras["metrics"]["stage_latency"]["retrieval"] = max(
        0,
        int((time.time() - retrieval_stage_started_at) * 1000),
    )

    memory_citations_list: List[Dict[str, Any]] = []
    for r in retrieved[:10]:
        cid = r.get("id")
        if cid:
            memory_citations_list.append({"id": cid, "kind": r.get("kind"), "score": float(r.get("score", 0.0))})
    response_extras["memory_citations"] = memory_citations_list
    response_extras["memory_used_count"] = int(len(memory_citations_list))

    # =================================================================
    # Stage 2b: WebSearch  (optional / best-effort)
    # =================================================================
    web_evidence: List[Dict[str, Any]] = []
    web_evidence_added = 0

    if not isinstance(evidence, list):
        evidence = list(evidence or [])

    params = _get_request_params(request)
    web_explicit = _to_bool(body.get("web")) or _to_bool(context.get("web")) or _to_bool(params.get("web"))
    want_web = web_explicit or bool(is_veritas_query) or any(
        k in qlower for k in ["agi", "research", "論文", "paper", "zenodo", "arxiv"]
    )

    web_max = body.get("web_max_results") or context.get("web_max_results") or 5
    try:
        web_max = int(web_max)
    except (ValueError, TypeError):
        web_max = 5
    web_max = max(1, min(20, web_max))

    response_extras.setdefault("metrics", {})
    if not isinstance(response_extras["metrics"], dict):
        response_extras["metrics"] = {}
    response_extras["metrics"].setdefault("web_hits", 0)
    response_extras["metrics"].setdefault("web_evidence_count", 0)

    should_run_web = bool(query and want_web and (not fast_mode or web_explicit or is_veritas_query))

    web_stage_started_at = time.time()
    if should_run_web and not mock_external_apis:
        ws = None
        ws_final_query = query

        try:
            ws0 = await _safe_web_search(query, max_results=web_max)
            ws = _normalize_web_payload(ws0)
        except Exception as e:  # subsystem resilience: intentionally broad
            response_extras.setdefault("env_tools", {})
            if isinstance(response_extras["env_tools"], dict):
                response_extras["env_tools"]["web_search_error"] = repr(e)

        if ws is None:
            response_extras["web_search"] = {"ok": True, "results": [], "degraded": True}
            ev_fallback = _norm_evidence_item(
                {
                    "source": "web",
                    "uri": "web:search",
                    "title": "web_search attempted (degraded)",
                    "snippet": f"[q={ws_final_query}] web_search unavailable or returned None",
                    "confidence": DEFAULT_CONFIDENCE,
                }
            )
            if ev_fallback:
                ev_fallback["source"] = "web"
                web_evidence.append(ev_fallback)
                evidence.append(ev_fallback)
                web_evidence_added = 1
        else:
            if isinstance(ws, dict) and "ok" not in ws:
                ws["ok"] = True
            try:
                meta = ws.get("meta") if isinstance(ws, dict) else None
                if isinstance(meta, dict):
                    ws_final_query = (
                        meta.get("final_query")
                        or meta.get("boosted_query")
                        or ws_final_query
                    )
                    meta.setdefault("final_query", ws_final_query)
            except (KeyError, TypeError, AttributeError):
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
                snippet = f"[q={ws_final_query}] {snippet}"
                try:
                    confidence = float(item.get("confidence", 0.7) or 0.7)
                except (ValueError, TypeError):
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
                    ev["source"] = "web"
                    web_evidence.append(ev)
                    evidence.append(ev)
                    web_evidence_added += 1

            try:
                ok_flag = bool(ws.get("ok")) if isinstance(ws, dict) else False
            except (KeyError, TypeError, AttributeError):
                ok_flag = False

            if ok_flag and web_evidence_added == 0:
                ev_fallback = _norm_evidence_item(
                    {
                        "source": "web",
                        "uri": "web:search",
                        "title": "web_search executed",
                        "snippet": f"[q={ws_final_query}] web_search ok=True but no structured results extracted",
                        "confidence": DEFAULT_CONFIDENCE,
                    }
                )
                if ev_fallback:
                    ev_fallback["source"] = "web"
                    web_evidence.append(ev_fallback)
                    evidence.append(ev_fallback)
                    web_evidence_added = 1

    elif should_run_web and mock_external_apis:
        response_extras["web_search"] = {
            "ok": True,
            "results": [],
            "mocked": True,
            "meta": {"reason": "replay_mock_external_apis"},
        }
        response_extras.setdefault("env_tools", {})
        if isinstance(response_extras["env_tools"], dict):
            response_extras["env_tools"]["web_search_mocked"] = True
    else:
        if want_web and "web_search" not in response_extras:
            response_extras["web_search"] = {
                "ok": False,
                "results": [],
                "skipped": True,
                "reason": "fast_mode",
            }

    response_extras["metrics"]["web_evidence_count"] = int(web_evidence_added)
    response_extras["metrics"]["stage_latency"]["web"] = max(
        0,
        int((time.time() - web_stage_started_at) * 1000),
    )

    # =================================================================
    # Stage 3: Options normalization
    # =================================================================
    explicit_raw = body.get("options") or body.get("alternatives") or []
    if not isinstance(explicit_raw, list):
        explicit_raw = []

    explicit_options: List[Dict[str, Any]] = [
        _norm_alt(a) for a in explicit_raw if isinstance(a, dict)
    ]
    explicit_options = [a for a in explicit_options if isinstance(a, dict)]

    input_alts: List[Dict[str, Any]] = list(explicit_options)

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
            _norm_alt({"id": "veritas_mvp_demo", "title": "MVPデモを最短で見せられる形にする", "description": "Swagger/CLIで /v1/decide の30〜60秒デモを作る。"}),
            _norm_alt({"id": "veritas_report", "title": "技術監査レポートを仕上げる", "description": "第三者が読めるレベルにブラッシュアップする。"}),
            _norm_alt({"id": "veritas_spec_sheet", "title": "MVP仕様書を1枚にまとめる", "description": "CLI/API・FUJI・Debate・Memoryの流れを1枚に整理する。"}),
            _norm_alt({"id": "veritas_demo_script", "title": "第三者向けデモ台本を作る", "description": "画面順・説明順・想定QAを台本化する。"}),
        ]

    alternatives: List[Dict[str, Any]] = list(input_alts)

    if not isinstance(web_evidence, list):
        web_evidence = []

    # =================================================================
    # Stage 4: Core decision + self-healing  (-> pipeline_execute)
    # =================================================================
    ctx.evidence = evidence
    ctx.input_alts = input_alts
    ctx.alternatives = alternatives
    ctx.explicit_options = explicit_options
    ctx.web_evidence = web_evidence
    ctx.retrieved = retrieved

    await stage_core_execute(
        ctx,
        call_core_decide_fn=call_core_decide,
        append_trust_log_fn=append_trust_log,
    )
    raw = ctx.raw

    # =================================================================
    # Stage 4b: Absorb raw results
    # =================================================================
    critique: Dict[str, Any] = {}
    debate: List[Any] = []
    telos: float = 0.0
    fuji_dict: Dict[str, Any] = {}
    modifications: List[Any] = []

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
        except (ValueError, TypeError):
            pass

        fuji_dict = raw.get("fuji") or fuji_dict

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

    # =================================================================
    # Stage 4c: Fallback alternatives
    # =================================================================
    alts: List[Dict[str, Any]] = alternatives or [
        _norm_alt({"title": "最小ステップで前進する"}),
        _norm_alt({"title": "情報収集を優先する"}),
        _norm_alt({"title": "今日は休息に充てる"}),
    ]
    alts = _dedupe_alts(alts)

    # =================================================================
    # Stage 4d: WorldModel + MemoryModel boost
    # =================================================================
    try:
        if world_model is not None and hasattr(world_model, "simulate"):
            boosted: List[Dict[str, Any]] = []
            uid_for_world = (context or {}).get("user_id") or user_id or "anon"
            uid_for_world = str(uid_for_world) if uid_for_world is not None else "anon"

            for d in alts:
                sim = world_model.simulate(user_id=uid_for_world, query=query, chosen=d)  # type: ignore
                if isinstance(sim, dict):
                    d["world"] = sim
                    micro = max(0.0, min(0.03, 0.02 * float(sim.get("utility", 0.0)) + 0.01 * float(sim.get("confidence", 0.5))))
                    d["score"] = float(d.get("score", 1.0)) * (1.0 + micro)
                boosted.append(d)
            alts = boosted
    except Exception as e:  # subsystem resilience
        _warn(f"[WorldModelOS] skip: {e}")

    try:
        response_extras.setdefault("metrics", {})
        if not isinstance(response_extras["metrics"], dict):
            response_extras["metrics"] = {}

        if MEM_VEC is not None and MEM_CLF is not None:
            response_extras["metrics"]["mem_model"] = {
                "applied": True, "reason": "loaded", "path": _mem_model_path(),
                "classes": getattr(MEM_CLF, "classes_", []).tolist() if hasattr(MEM_CLF, "classes_") else None,
            }
            for d in alts:
                text = (d.get("title") or "") + " " + (d.get("description") or "")
                p_allow = _allow_prob(text)
                base = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", base))
                d["score"] = base * (1.0 + 0.10 * p_allow)
        else:
            response_extras["metrics"]["mem_model"] = {"applied": False, "reason": "model_not_loaded", "path": _mem_model_path()}
    except (ValueError, TypeError, AttributeError) as e:
        response_extras.setdefault("metrics", {})
        if not isinstance(response_extras["metrics"], dict):
            response_extras["metrics"] = {}
        response_extras["metrics"]["mem_model"] = {"applied": False, "error": str(e), "path": _mem_model_path()}

    # chosen (pre-debate)
    chosen = raw.get("chosen") if isinstance(raw, dict) else {}
    if not isinstance(chosen, dict) or not chosen:
        try:
            chosen = max(alts, key=lambda d: float((d.get("world") or {}).get("utility", d.get("score", 1.0))))
        except (ValueError, TypeError):
            chosen = alts[0] if alts else {}

    # =================================================================
    # Stage 5: DebateOS  (best-effort)
    # =================================================================
    debate_result: Dict[str, Any] = {}
    try:
        if debate_core is not None and hasattr(debate_core, "run_debate") and not fast_mode:
            debate_result = debate_core.run_debate(  # type: ignore
                query=query, options=alts,
                context={"user_id": user_id, "stakes": (context or {}).get("stakes"), "telos_weights": (context or {}).get("telos_weights")},
            ) or {}
    except (KeyError, TypeError, AttributeError) as e:
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
            except (KeyError, TypeError, AttributeError):
                pass
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
        except (KeyError, TypeError, AttributeError) as e:
            _warn(f"[DebateOS] risk_delta heuristic skipped: {e}")

    # =================================================================
    # Stage 5b: Critique  (post-debate, pre-FUJI)
    # =================================================================
    try:
        critique = _normalize_critique_payload(critique)
        if not critique:
            critique = await _run_critique_best_effort(
                query=query, chosen=chosen,
                evidence=evidence if isinstance(evidence, list) else [],
                debate=debate, context=context, user_id=user_id,
            )
        critique = _ensure_critique_required(
            response_extras=response_extras, query=query, chosen=chosen, critique_obj=critique,
        )
    except Exception:  # subsystem resilience: intentionally broad
        critique = _critique_fallback(reason="critique_guard_exception", query=query, chosen=chosen)
        response_extras.setdefault("env_tools", {})
        if isinstance(response_extras["env_tools"], dict):
            response_extras["env_tools"]["critique_degraded"] = True

    try:
        if isinstance(critique, dict) and critique.get("ok") is False:
            response_extras.setdefault("env_tools", {})
            if isinstance(response_extras["env_tools"], dict):
                response_extras["env_tools"]["review_required"] = True
                response_extras["env_tools"]["review_reason"] = "critique_missing_or_failed"
    except (KeyError, TypeError, AttributeError):
        pass

    # =================================================================
    # Stage 6: Policy (FUJI + ValueCore + Gate)  (-> pipeline_policy)
    # =================================================================
    ctx.fuji_dict = fuji_dict
    ctx.evidence = evidence
    ctx.alternatives = alts
    ctx.input_alts = input_alts
    ctx.telos = telos
    ctx.debate = debate
    ctx.response_extras = response_extras

    stage_fuji_precheck(ctx)

    stage_value_core(ctx, _load_valstats=_load_valstats, _clip01=_clip01)

    stage_gate_decision(ctx)

    # Sync back from ctx
    fuji_dict = ctx.fuji_dict
    evidence = ctx.evidence
    alts = ctx.alternatives
    input_alts = ctx.input_alts
    telos = ctx.telos
    response_extras = ctx.response_extras
    decision_status = ctx.decision_status
    rejection_reason = ctx.rejection_reason
    modifications = ctx.modifications
    effective_risk = ctx.effective_risk
    value_ema = ctx.value_ema
    telos_threshold = ctx.telos_threshold
    values_payload = ctx.values_payload
    if ctx.decision_status == "rejected":
        chosen = ctx.chosen
        alts = ctx.alternatives

    # =================================================================
    # Stage 6b: Value learning EMA update
    # =================================================================
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
    except (ValueError, TypeError) as e:
        _warn(f"[value-learning] skip: {e}")

    # =================================================================
    # Stage 6c: Metrics
    # =================================================================
    duration_ms = max(1, int((time.time() - started_at) * 1000))
    mem_evi_cnt = 0
    for ev in evidence:
        if isinstance(ev, dict) and str(ev.get("source", "")).startswith("memory"):
            mem_evi_cnt += 1
    response_extras.setdefault("metrics", {})
    if not isinstance(response_extras["metrics"], dict):
        response_extras["metrics"] = {}
    response_extras["metrics"].update({
        "latency_ms": duration_ms,
        "mem_evidence_count": int(mem_evi_cnt),
        "memory_evidence_count": int(response_extras["metrics"].get("memory_evidence_count", 0) or 0),
        "alts_count": int(len(alts)),
        "has_evidence": bool(evidence),
        "value_ema": round(float(value_ema), 4),
        "effective_risk": round(float(effective_risk), 4),
        "telos_threshold": round(float(telos_threshold), 3),
    })
    _ensure_full_contract(response_extras, fast_mode_default=fast_mode, context_obj=context, query_str=query)

    # =================================================================
    # Stage 6d: Low-evidence hardening
    # =================================================================
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
    except (ValueError, TypeError):
        pass

    evidence = [ev for ev in (_norm_evidence_item(x) for x in evidence) if ev]  # type: ignore[misc]
    evidence = _dedupe_evidence(evidence)
    EVIDENCE_MAX = int(os.getenv("VERITAS_EVIDENCE_MAX", "50"))
    if len(evidence) > EVIDENCE_MAX:
        evidence = evidence[:EVIDENCE_MAX]

    # =================================================================
    # Stage 7: Response assembly  (-> pipeline_response)
    # =================================================================
    ctx.chosen = chosen
    ctx.alternatives = alts
    ctx.critique = critique
    ctx.debate = debate
    ctx.telos = telos
    ctx.fuji_dict = fuji_dict
    ctx.evidence = evidence
    ctx.response_extras = response_extras
    ctx.decision_status = decision_status
    ctx.rejection_reason = rejection_reason
    ctx.modifications = modifications
    ctx.effective_risk = effective_risk
    ctx.values_payload = values_payload
    ctx.raw = raw

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
    finalize_evidence(payload, web_evidence=web_evidence, evidence_max=EVIDENCE_MAX)

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
    build_replay_snapshot(ctx, payload, should_run_web=should_run_web)

    return payload
