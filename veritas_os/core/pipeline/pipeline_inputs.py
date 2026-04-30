# veritas_os/core/pipeline_inputs.py
# -*- coding: utf-8 -*-
"""
Pipeline input normalization stage.

Parses the incoming DecideRequest + Request into a :class:`PipelineContext`
with all fields validated, sanitised and defaults applied.
"""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Dict

from .pipeline_types import PipelineContext
from .pipeline_helpers import _to_bool_local, _lazy_import, _now_iso, _warn
from .pipeline_contracts import _ensure_full_contract

logger = logging.getLogger(__name__)

# ---- Private‑field prefixes that users must not inject ----
_PIPELINE_PRIVATE_PREFIXES = (
    "_pipeline_",
    "_orchestrated_by_pipeline",
    "_episode_saved",
    "_world_state_",
    "_daily_plans_",
    "_world_sim_result",
)
_TEST_ONLY_PRE_BIND_SIGNAL_KEY = "pre_bind_participation_signal"


def _to_bool(v: Any) -> bool:
    return _to_bool_local(v)


def normalize_pipeline_inputs(
    req: Any,
    request: Any,
    *,
    _get_request_params: Any = None,
    _to_dict_fn: Any = None,
) -> PipelineContext:
    """Parse *req* and *request* into a fully normalised :class:`PipelineContext`.

    Parameters
    ----------
    _get_request_params:
        Callable to extract query‑params from the request object.
    _to_dict_fn:
        Callable to convert arbitrary objects to dict.
    """
    started_at = time.time()

    # --- body ---
    if _to_dict_fn is None:
        def _to_dict_fn(o: Any) -> Dict[str, Any]:  # type: ignore[misc]
            """Inline fallback when no _to_dict_fn is injected."""
            if isinstance(o, dict):
                return o
            if hasattr(o, "model_dump"):
                return o.model_dump(exclude_none=True)
            if hasattr(o, "dict"):
                return o.dict()
            if hasattr(o, "__dict__"):
                return dict(o.__dict__)
            return {}
    body = req.model_dump() if hasattr(req, "model_dump") else _to_dict_fn(req)
    if not isinstance(body, dict):
        body = {}

    # --- context ---
    context: Dict[str, Any] = body.get("context") or {}
    if not isinstance(context, dict):
        context = {}

    # Strip pipeline‑private keys from user‑supplied context
    injected = [
        k
        for k in list(context.keys())
        if isinstance(k, str) and any(k.startswith(p) for p in _PIPELINE_PRIVATE_PREFIXES)
    ]
    if injected:
        logger.warning(
            "Pipeline private fields stripped from user-supplied context: %s",
            sorted(injected),
        )
        for k in injected:
            context.pop(k, None)

    replay_mode = bool(context.get("_replay_mode", False))
    mock_external_apis = bool(context.get("_mock_external_apis", replay_mode))
    if replay_mode:
        body["temperature"] = body.get("temperature", 0)

    # --- query ---
    raw_query = body.get("query") or context.get("query") or ""
    if not isinstance(raw_query, str):
        raw_query = str(raw_query)
    query = raw_query.strip()

    # --- user_id (always str) ---
    user_id_raw = context.get("user_id") or body.get("user_id") or "anon"
    user_id = str(user_id_raw) if user_id_raw is not None else "anon"

    # --- fast mode ---
    if _get_request_params is None:
        def _get_request_params(request: Any) -> Dict[str, Any]:  # type: ignore[misc]
            """Inline fallback when no _get_request_params is injected."""
            out: Dict[str, Any] = {}
            qp = getattr(request, "query_params", None)
            if qp is not None:
                out.update(dict(qp))
            pm = getattr(request, "params", None)
            if pm is not None:
                out.update(dict(pm))
            return out
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

    # --- response extras (initial contract) ---
    response_extras: Dict[str, Any] = {
        "metrics": {
            "mem_hits": 0,
            "memory_evidence_count": 0,
            "web_hits": 0,
            "web_evidence_count": 0,
            "fast_mode": False,
            "mem_evidence_count": 0,
            "stage_latency": {
                "retrieval": 0,
                "web": 0,
                "llm": 0,
                "gate": 0,
                "persist": 0,
            },
        },
        "fast_mode": False,
        "env_tools": {},
    }
    response_extras["fast_mode"] = fast_mode
    response_extras["metrics"]["fast_mode"] = fast_mode
    response_extras["memory_meta"] = {"context": dict(context)}

    # Canonical pre-bind deterministic seam:
    # Keep production semantics unchanged (absent by default), while allowing
    # reliability tests to inject participation signal at the request-input
    # boundary instead of patching call_core_decide/raw extras.
    pre_bind_signal = context.get(_TEST_ONLY_PRE_BIND_SIGNAL_KEY)
    if isinstance(pre_bind_signal, dict):
        response_extras["participation_signal"] = dict(pre_bind_signal)

    # --- WorldOS: inject state ---
    world_model = (
        _lazy_import("veritas_os.core.world", None)
        or _lazy_import("veritas_os.core.world_model", None)
    )
    try:
        if world_model is not None and hasattr(world_model, "inject_state_into_context"):
            context = world_model.inject_state_into_context(context, user_id)  # type: ignore
            body["context"] = context
    except Exception as e:  # subsystem resilience: intentionally broad
        _warn(f"[WorldOS] inject_state_into_context skipped: {e}")

    try:
        response_extras["memory_meta"] = {"context": dict(context)}
    except Exception:  # subsystem resilience: intentionally broad
        pass

    # early contract hardening
    _ensure_full_contract(response_extras, fast_mode_default=fast_mode, context_obj=context, query_str=query)

    qlower = query.lower()
    is_veritas_query = any(
        k in qlower for k in ["veritas", "agi", "protoagi", "プロトagi", "veritasのagi化"]
    )

    # --- PlannerOS ---
    plan: Dict[str, Any] = {"steps": [], "raw": None, "source": "fallback"}
    try:
        plan_fn = _lazy_import("veritas_os.core.planner", "plan_for_veritas_agi")
        if callable(plan_fn):
            p = plan_fn(context=context, query=query)  # type: ignore[misc]
            if isinstance(p, dict):
                plan = p or plan
        _warn(f"[PlannerOS] steps={len(plan.get('steps', []))}, source={plan.get('source')}")
    except Exception as e:  # subsystem resilience: intentionally broad
        _warn(f"[PlannerOS] skipped: {e}")

    response_extras["planner"] = {
        "steps": plan.get("steps", []) if isinstance(plan, dict) else [],
        "raw": plan.get("raw") if isinstance(plan, dict) else None,
        "source": plan.get("source") if isinstance(plan, dict) else "fallback",
    }

    # --- request_id ---
    if replay_mode:
        request_id = str(
            body.get("request_id") or context.get("request_id") or secrets.token_hex(16)
        )
    else:
        request_id = body.get("request_id") or secrets.token_hex(16)

    # --- seed / min_evidence ---
    seed_raw = body.get("seed")
    try:
        seed = int(seed_raw) if seed_raw is not None else 0
    except (ValueError, TypeError):
        seed = 0
    # NOTE: Previously ``random.seed(seed)`` was called here, which mutated
    # the process-global random state and could affect concurrent requests.
    # The seed value is stored in ``ctx.seed`` for deterministic downstream use.

    try:
        min_ev = int(body.get("min_evidence") or 1)
    except (ValueError, TypeError):
        min_ev = 1
    if min_ev < 1:
        min_ev = 1

    return PipelineContext(
        body=body,
        query=query,
        user_id=user_id,
        request_id=request_id,
        fast_mode=fast_mode,
        replay_mode=replay_mode,
        mock_external_apis=mock_external_apis,
        seed=seed,
        min_ev=min_ev,
        started_at=started_at,
        is_veritas_query=is_veritas_query,
        context=context,
        response_extras=response_extras,
        plan=plan,
    )
