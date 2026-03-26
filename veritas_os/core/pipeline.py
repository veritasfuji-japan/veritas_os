# veritas_os/core/pipeline.py
# -*- coding: utf-8 -*-
"""
VERITAS Decision Pipeline – Orchestrator (core/pipeline.py)

Public contract:
- ``run_decide_pipeline(req, request)`` is the stable entry-point used by
  the API layer for ``/v1/decide``.
- This module owns orchestration only; stage-specific shaping, gating, and
  persistence should stay in the dedicated pipeline_* helper modules.

Preferred extension points:
- ``pipeline_inputs`` for request normalization
- ``pipeline_execute`` for kernel execution / self-healing
- ``pipeline_policy`` for FUJI / ValueCore policy steps
- ``pipeline_response`` for response assembly
- ``pipeline_persist`` and ``pipeline_replay`` for persistence / replay

Compatibility guidance:
- Pure utility functions (to_dict, _norm_alt, get_request_params, etc.) have
  been moved to ``pipeline_compat.py`` and are re-exported here for backward
  compatibility.  All existing ``from veritas_os.core.pipeline import X``
  paths continue to work.
- Web search core logic has been moved to ``pipeline_web_adapter.safe_web_search``
  with a dependency-injection pattern.  ``_safe_web_search`` here is a thin
  wrapper that resolves the web_search function from module-level state,
  preserving monkeypatch support.
- Extend helpers first, and treat local compatibility wrappers here as
  adapters rather than a place for new policy branches or fallback-heavy logic.

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
  pipeline_compat   – backward-compat utility functions (to_dict, _norm_alt, etc.)

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

from __future__ import annotations

import inspect  # noqa: F401 – re-exported; tests access pipeline.inspect
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from .utils import (  # noqa: F401 – _redact_text/redact_payload re-exported for backward compat
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
    safe_web_search as _safe_web_search_impl,
)
from .pipeline_contracts import (
    _ensure_full_contract,
    _ensure_metrics_contract,
    _deep_merge_dict,
    _merge_extras_preserving_contract,
)
from .pipeline_signature_adapter import (  # noqa: F401 – re-exported for backward compat
    call_core_decide,
)
from .pipeline_compat import (  # noqa: F401 – re-exported for backward compat
    _to_bool,
    _to_float_or,
    _clip01,
    to_dict,
    _to_dict,
    get_request_params,
    _get_request_params,
    _norm_alt,
    _fallback_load_persona,
)
from .pipeline_persistence import (
    REPO_ROOT,
    _UNSAFE_UNICODE_CATEGORIES,
    _SAFE_FILENAME_RE,
    _safe_paths,
    _fallback_build_dataset_record,
    _fallback_append_dataset_record,
    load_dataset_writer as _load_dataset_writer,
    _fallback_append_trust_log,
    _fallback_write_shadow_decide,
    load_trust_log as _load_trust_log,
    _EVIDENCE_MAX_UPPER,
    resolve_evidence_max as _resolve_evidence_max,
)
from .pipeline_gate import (
    MEM_VEC,
    MEM_CLF,
    predict_gate_label,
    _mem_model_path,
    _load_valstats as _load_valstats_impl,
    _save_valstats as _save_valstats_impl,
    _dedupe_alts_fallback,
    _dedupe_alts as _dedupe_alts_impl,
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

_atomic_write_json: Any = None
_HAS_ATOMIC_IO = False
try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    _HAS_ATOMIC_IO = True
except (ImportError, ModuleNotFoundError):
    pass


Request: Any = None  # fallback: tests may import pipeline without fastapi installed
try:
    from fastapi import Request
except (ImportError, ModuleNotFoundError):
    pass


# =========================================================
# repo root / time helpers
# =========================================================

# REPO_ROOT, _UNSAFE_UNICODE_CATEGORIES -> pipeline_persistence.py に移動済み（上部 import）
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

# _to_bool -> pipeline_compat.py に移動済み（上部 import で re-export 済み）


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
veritas_core: Any = None
try:
    from . import kernel as veritas_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[ERROR][pipeline] kernel import failed (REQUIRED): {repr(e)}")

# ---- fuji (REQUIRED) ----
fuji_core: Any = None
try:
    from . import fuji as fuji_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[ERROR][pipeline] fuji import failed (REQUIRED): {repr(e)}")

# ---- memory (RECOMMENDED) ----
mem: Any = None
try:
    from . import memory as mem
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] memory import failed (RECOMMENDED): {repr(e)}")

# ---- value_core (RECOMMENDED) ----
value_core: Any = None
try:
    from . import value_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] value_core import failed (RECOMMENDED): {repr(e)}")

# ---- world model (RECOMMENDED) ----
world_model: Any = None
try:
    from . import world as world_model
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] world import failed (RECOMMENDED): {repr(e)}")

# ---- reason (OPTIONAL) ----
reason_core: Any = None
try:
    from . import reason as reason_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[INFO][pipeline] reason import failed (OPTIONAL): {repr(e)}")

# ---- debate (RECOMMENDED) ----
debate_core: Any = None
try:
    from . import debate as debate_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] debate import failed (RECOMMENDED): {repr(e)}")


# =========================================================
# Safe imports (API schemas / persona)
# =========================================================

DecideRequest: Any = None
DecideResponse: Any = None
try:
    from veritas_os.api.schemas import DecideRequest, DecideResponse
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] api.schemas import failed: {repr(e)}")


# _fallback_load_persona -> pipeline_compat.py に移動済み（上部 import で re-export 済み）

load_persona: Any = _fallback_load_persona
try:
    from veritas_os.api.evolver import load_persona
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    pass

_mask_pii: Any = None
_HAS_SANITIZE = False
try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii
    _HAS_SANITIZE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover
    pass


# =========================================================
# Utility functions -> pipeline_compat.py に移動済み
# to_dict, _to_dict, get_request_params, _get_request_params,
# _norm_alt, _clip01, _to_float_or, _to_bool, _fallback_load_persona
# 上部 import で re-export 済み。既存の import path は維持される。
# =========================================================


def _get_memory_store() -> Optional[Any]:
    """pipeline.mem を参照するラッパー（テストが monkeypatch で pipeline.mem をパッチ可能にする）。"""
    if mem is None:
        return None
    return _get_memory_store_impl(mem=mem)


# _safe_paths, EVIDENCE_MAX, _SAFE_FILENAME_RE -> pipeline_persistence.py に移動済み
LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG = _safe_paths(_warn=_warn)
REPLAY_REPORT_DIR = (REPO_ROOT / "audit" / "replay_reports").resolve()
EVIDENCE_MAX = _resolve_evidence_max()

# ★ Replay functions moved to pipeline_replay.py.
# _safe_filename_id, _sanitize_for_diff, _build_replay_diff,
# _load_persisted_decision, _ReplayRequest are imported above for backward compat.
# _SAFE_FILENAME_RE imported from pipeline_persistence for direct-access backward compat.


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
# Safe dataset writer (optional) -> pipeline_persistence.py に移動済み
# =========================================================
build_dataset_record, append_dataset_record = _load_dataset_writer(_warn=_warn)


# =========================================================
# Trust log (optional; fallback-safe) -> pipeline_persistence.py に移動済み
# =========================================================
append_trust_log, write_shadow_decide = _load_trust_log()


# =========================================================
# MemoryModel / gate / valstats / dedup -> pipeline_gate.py に移動済み
# MEM_VEC, MEM_CLF, predict_gate_label, _mem_model_path, _allow_prob,
# _dedupe_alts_fallback are imported above for backward compat.
# =========================================================

# Wrapper functions that close over module-level state.
# Tests monkeypatch module-level variables (e.g. predict_gate_label,
# veritas_core, VAL_JSON), so these wrappers must reference the
# module-level names at *call time*, not import time.


def _allow_prob(text: str) -> float:
    """Wrapper that uses module-level predict_gate_label (patchable by tests)."""
    d = predict_gate_label(text)
    try:
        return float(d.get("allow", 0.0))
    except (ValueError, TypeError, AttributeError):
        return 0.0


def _load_valstats() -> Dict[str, Any]:
    return _load_valstats_impl(VAL_JSON)


def _save_valstats(d: Dict[str, Any]) -> None:
    """Save value stats to VAL_JSON.

    Uses atomic_write_json when available, otherwise falls back to
    tempfile + os.replace for crash-safe persistence.
    """
    _save_valstats_impl(d, VAL_JSON, _HAS_ATOMIC_IO=_HAS_ATOMIC_IO, _atomic_write_json=_atomic_write_json)


def _dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Wrapper that passes module-level veritas_core (patchable by tests).

    Re-implements the kernel-first logic here so that debug logs go to
    the ``veritas_os.core.pipeline`` logger (expected by existing tests).
    """
    try:
        if veritas_core is not None and hasattr(veritas_core, "_dedupe_alts"):
            result = veritas_core._dedupe_alts(alts)
            if isinstance(result, list):
                return result
            logger.debug(
                "_dedupe_alts: kernel helper returned %s, expected list",
                type(result).__name__,
            )
    except Exception:
        logger.debug(
            "_dedupe_alts: kernel helper failed, using fallback", exc_info=True
        )
    return _dedupe_alts_fallback(alts)


# call_core_decide -> pipeline_signature_adapter.py に移動済み（上部 import）


# =========================================================
# Memory adapter -> pipeline_memory_adapter.py に移動済み
# (_get_memory_store, _call_with_accepted_kwargs, _memory_has,
#  _memory_search, _memory_put, _memory_add_usage)
# =========================================================


# =========================================================
# Optional: WebSearch adapter (do not crash import)
# =========================================================

_tool_web_search: Any = None
try:
    from veritas_os.tools.web_search import web_search as _tool_web_search
except (ImportError, ModuleNotFoundError):
    pass  # optional dependency / env missing in CI or local


def _resolve_web_search_fn() -> Any:
    """Resolve web_search callable at call time (monkeypatch-safe).

    Resolution order:
      1. module-level ``web_search`` (set by monkeypatch in tests)
      2. ``_tool_web_search`` (imported from tools.web_search)
    """
    import sys
    _this = sys.modules[__name__]
    fn = getattr(_this, "web_search", None)
    if callable(fn):
        return fn
    return getattr(_this, "_tool_web_search", None)


async def _safe_web_search(query: str, *, max_results: int = 5) -> Optional[dict]:
    """Returns web_search result dict or None (never raises).

    Core logic is in ``pipeline_web_adapter.safe_web_search``.
    This thin wrapper resolves the web_search function from module-level
    state at call time, preserving monkeypatch support for tests.
    """
    return await _safe_web_search_impl(
        query,
        max_results=max_results,
        web_search_resolver=_resolve_web_search_fn,
    )


# _normalize_web_payload -> pipeline_web_adapter.py に移動済み

# =========================================================
# evidence.py -> pipeline item
# =========================================================
evidence_core: Any = None
try:
    from veritas_os.core import evidence as evidence_core
except (ImportError, ModuleNotFoundError) as e:  # pragma: no cover
    _warn(f"[WARN][pipeline] evidence import failed (OPTIONAL): {repr(e)}")

# _norm_evidence_item_simple, _evidencepy_to_pipeline_item ->
# pipeline_evidence.py に移動済み（上部 import で re-export 済み）


# =========================================================
# main pipeline (FULL / hardened) - Orchestrator
# =========================================================

async def run_decide_pipeline(
    req: DecideRequest,
    request: Request,
    *,
    memory_store_getter: Optional[Callable] = None,
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

    pipeline_started_at = time.time()
    _stage_failures: List[str] = []  # track degraded stages for observability

    # Allow callers (e.g. replay engine) to override memory store getter
    effective_get_memory_store = memory_store_getter or _get_memory_store

    # =================================================================
    # Stage 1: Input normalization  (-> pipeline_inputs)
    # =================================================================
    ctx = normalize_pipeline_inputs(
        req,
        request,
        _get_request_params=_get_request_params,
        _to_dict_fn=to_dict,
    )

    # =================================================================
    # Stage 2: MemoryOS retrieval  (-> pipeline_retrieval)
    # =================================================================
    stage_memory_retrieval(
        ctx,
        _get_memory_store=effective_get_memory_store,
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
    try:
        persist_audit_log(ctx, append_trust_log_fn=append_trust_log, write_shadow_decide_fn=write_shadow_decide)
    except Exception as e:
        _stage_failures.append(f"audit_log:{type(e).__name__}")
        logger.warning("[pipeline] audit_log persist failed (best-effort): %s", e)

    try:
        persist_to_memory(ctx, payload, _get_memory_store=effective_get_memory_store, _memory_put=_memory_put)
    except Exception as e:
        _stage_failures.append(f"memory_persist:{type(e).__name__}")
        logger.warning("[pipeline] memory persist failed (best-effort): %s", e)

    try:
        persist_reason_and_reflection(
            ctx, payload,
            VAL_JSON=VAL_JSON, META_LOG=META_LOG,
            _load_valstats=_load_valstats, _save_valstats=_save_valstats,
        )
    except Exception as e:
        _stage_failures.append(f"reason_reflection:{type(e).__name__}")
        logger.warning("[pipeline] reason/reflection persist failed (best-effort): %s", e)

    # FINALIZE evidence
    finalize_evidence(payload, web_evidence=ctx.web_evidence, evidence_max=EVIDENCE_MAX)

    duration_ms = max(1, int((time.time() - ctx.started_at) * 1000))
    try:
        persist_decision_to_disk(
            ctx, payload, duration_ms=duration_ms,
            LOG_DIR=LOG_DIR, DATASET_DIR=DATASET_DIR,
            _HAS_ATOMIC_IO=_HAS_ATOMIC_IO, _atomic_write_json=_atomic_write_json,
        )
    except Exception as e:
        _stage_failures.append(f"disk_persist:{type(e).__name__}")
        logger.warning("[pipeline] disk persist failed (best-effort): %s", e)

    try:
        persist_world_state(ctx, payload)
    except Exception as e:
        _stage_failures.append(f"world_state:{type(e).__name__}")
        logger.warning("[pipeline] world_state persist failed (best-effort): %s", e)

    try:
        persist_dataset_record(
            ctx, payload, duration_ms=duration_ms,
            build_dataset_record_fn=build_dataset_record,
            append_dataset_record_fn=append_dataset_record,
        )
    except Exception as e:
        _stage_failures.append(f"dataset_record:{type(e).__name__}")
        logger.warning("[pipeline] dataset_record persist failed (best-effort): %s", e)

    # =================================================================
    # Stage 8b: Replay snapshot
    # =================================================================
    should_run_web = getattr(ctx, "_should_run_web", False)
    try:
        build_replay_snapshot(ctx, payload, should_run_web=should_run_web)
    except Exception as e:
        _stage_failures.append(f"replay_snapshot:{type(e).__name__}")
        logger.warning("[pipeline] replay snapshot failed (best-effort): %s", e)

    # =================================================================
    # Observability: record pipeline health summary
    # =================================================================
    total_ms = max(1, int((time.time() - pipeline_started_at) * 1000))
    extras = payload.setdefault("extras", {})
    if isinstance(extras, dict):
        metrics = extras.setdefault("metrics", {})
        if isinstance(metrics, dict):
            metrics["pipeline_total_ms"] = total_ms
            if _stage_failures:
                metrics["degraded_stages"] = _stage_failures
    if _stage_failures:
        logger.info(
            "[pipeline] completed with degraded stages (%d ms): %s",
            total_ms,
            ", ".join(_stage_failures),
        )

    return payload
