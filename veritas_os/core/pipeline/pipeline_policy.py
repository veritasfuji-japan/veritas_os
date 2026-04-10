# veritas_os/core/pipeline_policy.py
# -*- coding: utf-8 -*-
"""
Pipeline policy / gate application stage.

Handles:
- FUJI pre‑check
- ValueCore evaluation
- Gate decision (allow / modify / rejected)
- Value EMA learning
"""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone
import hashlib
from typing import Any

from veritas_os.policy.evaluator import evaluate_runtime_policies
from veritas_os.policy.runtime_adapter import load_runtime_bundle

from .pipeline_types import (
    PipelineContext,
    HIGH_RISK_THRESHOLD,
    BASE_TELOS_THRESHOLD,
    TELOS_THRESHOLD_MIN,
    TELOS_THRESHOLD_MAX,
)
from .pipeline_helpers import _lazy_import, _apply_value_boost, _warn
from .pipeline_evidence import _norm_evidence_item

logger = logging.getLogger(__name__)


def _build_fail_closed_fuji_precheck(reason: str) -> dict[str, Any]:
    """Return a fail-closed FUJI payload used when safety evaluation fails."""
    return {
        "status": "rejected",
        "reasons": [reason],
        "violations": ["fuji_precheck_unavailable"],
        "risk": 1.0,
        "modifications": [],
    }


def _coerce_policy_enforce_flag(raw_value: Any) -> bool:
    """Normalize explicit/runtime enforcement values into bool."""
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in ("1", "true", "yes")
    return bool(raw_value)


def _resolve_rollout_controls(decision: dict[str, Any]) -> dict[str, Any]:
    """Extract rollout controls from the first triggered policy metadata."""
    policy_results = decision.get("policy_results", [])
    if not isinstance(policy_results, list):
        return {}

    for result in policy_results:
        if not isinstance(result, dict) or not result.get("triggered"):
            continue
        metadata = result.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        rollout_controls = metadata.get("rollout_controls", {})
        if isinstance(rollout_controls, dict):
            return rollout_controls
    return {}


def _resolve_rollback_metadata(decision: dict[str, Any]) -> dict[str, Any]:
    """Extract rollback metadata from the first triggered policy."""
    policy_results = decision.get("policy_results", [])
    if not isinstance(policy_results, list):
        return {}

    for result in policy_results:
        if not isinstance(result, dict) or not result.get("triggered"):
            continue
        metadata = result.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        rollback = metadata.get("rollback", {})
        if isinstance(rollback, dict):
            return rollback
    return {}


def _deterministic_bucket_ratio(bucket_key: str) -> float:
    """Return deterministic ratio [0, 1) from a bucket key."""
    digest = hashlib.sha256(bucket_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _is_rollout_auto_promoted(rollout_controls: dict[str, Any]) -> bool:
    """Return True when canary rollout should auto-promote to full."""
    full_after = rollout_controls.get("full_enforce_after")
    if not isinstance(full_after, str) or not full_after.strip():
        return False
    normalized = full_after.strip().replace("Z", "+00:00")
    try:
        full_after_dt = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("invalid full_enforce_after in rollout_controls: %r", full_after)
        return False
    if full_after_dt.tzinfo is None:
        full_after_dt = full_after_dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= full_after_dt


def _is_enforcement_enabled_for_rollout(
    ctx_dict: dict[str, Any],
    decision: dict[str, Any],
) -> tuple[bool, str]:
    """Resolve runtime enforcement state with canary/full rollout control."""
    enforce = ctx_dict.get("policy_runtime_enforce")
    if enforce is None:
        raw = os.getenv("VERITAS_POLICY_RUNTIME_ENFORCE")
        if raw is not None:
            enforce = raw
        else:
            # Fall back to posture-derived default.
            try:
                from veritas_os.core.posture import get_active_posture
                enforce = get_active_posture().policy_runtime_enforce
            except Exception:
                enforce = ""
    if not _coerce_policy_enforce_flag(enforce):
        return False, "enforcement_disabled"

    rollout_controls = _resolve_rollout_controls(decision)
    strategy = str(rollout_controls.get("strategy", "full")).strip().lower()
    if strategy in {"", "full"}:
        return True, "full"
    if strategy == "disabled":
        return False, "rollout_disabled"
    if strategy in {"canary", "staged"}:
        if _is_rollout_auto_promoted(rollout_controls):
            return True, "full_auto_promoted"
        canary_percent_raw = rollout_controls.get("canary_percent", 0)
        try:
            canary_percent = int(canary_percent_raw)
        except (TypeError, ValueError):
            logger.warning(
                "invalid canary_percent in rollout_controls: %r",
                canary_percent_raw,
            )
            canary_percent = 0
        canary_percent = max(0, min(100, canary_percent))
        bucket_key = str(
            ctx_dict.get("policy_rollout_key")
            or ctx_dict.get("request_id")
            or ctx_dict.get("trace_id")
            or ctx_dict.get("actor")
            or ""
        )
        ratio = _deterministic_bucket_ratio(bucket_key)
        in_canary = ratio < (canary_percent / 100.0)
        if not in_canary:
            return False, f"{strategy}_skip"
        return True, strategy

    logger.warning(
        "unknown rollout strategy=%r; defaulting to safe full enforcement",
        strategy,
    )
    return True, "full_unknown_strategy"


def _apply_compiled_policy_runtime_bridge(ctx: PipelineContext) -> None:
    """Evaluate optional compiled policy bundle and expose structured output.

    Integration point:
    - `ctx.context["compiled_policy_bundle_dir"]` may point to a compiled bundle.
    - Result is written to `ctx.response_extras["governance"]["compiled_policy"]`.
    - Enforcement is opt-in via `ctx.context["policy_runtime_enforce"]`.
    """
    bundle_dir = (ctx.context or {}).get("compiled_policy_bundle_dir")
    if not bundle_dir:
        return

    ctx_dict = ctx.context or {}

    try:
        runtime_bundle = load_runtime_bundle(bundle_dir)
        decision = evaluate_runtime_policies(runtime_bundle, ctx_dict).to_dict()
    except (OSError, ValueError) as exc:
        logger.warning("compiled policy runtime bridge failed: %s", exc)
        return
    except (TypeError, KeyError) as exc:
        logger.error(
            "compiled policy runtime bridge unexpected error (possible bug): %s",
            exc,
            exc_info=True,
        )
        return

    governance = ctx.response_extras.setdefault("governance", {})
    if not isinstance(governance, dict):
        governance = {}
        ctx.response_extras["governance"] = governance
    governance["compiled_policy"] = decision
    signing = runtime_bundle.manifest.get("signing", {})
    signing_algorithm = str(signing.get("algorithm", "sha256")).strip().lower()
    signer_id = str(signing.get("key_id", "")).strip()
    ctx.governance_identity = {
        "policy_version": runtime_bundle.version,
        "digest": runtime_bundle.semantic_hash,
        "signature_verified": signing_algorithm == "ed25519",
        "signer_id": signer_id,
        "verified_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }

    outcome = decision.get("final_outcome")
    rollback_metadata = _resolve_rollback_metadata(decision)
    enforce, rollout_state = _is_enforcement_enabled_for_rollout(ctx_dict, decision)
    governance["compiled_policy_rollout"] = {
        "enforced": enforce,
        "state": rollout_state,
        "rollback": rollback_metadata,
    }
    if not enforce:
        if outcome in {"deny", "halt", "escalate", "require_human_review"}:
            logger.warning(
                "compiled policy outcome=%s observed but not enforced "
                "(policy_runtime_enforce=false, rollout_state=%s)",
                outcome,
                rollout_state,
            )
        return

    if outcome in {"deny", "halt"}:
        ctx.fuji_dict["status"] = "rejected"
        ctx.fuji_dict.setdefault("reasons", []).append(
            f"compiled_policy:{outcome}"
        )
        logger.info(
            "compiled policy enforcement: outcome=%s → status=rejected (policies=%s)",
            outcome,
            decision.get("triggered_policies", []),
        )
    elif outcome in {"escalate", "require_human_review"}:
        ctx.fuji_dict["status"] = "modify"
        ctx.fuji_dict.setdefault("reasons", []).append(
            f"compiled_policy:{outcome}"
        )
        logger.info(
            "compiled policy enforcement: outcome=%s → status=modify (policies=%s)",
            outcome,
            decision.get("triggered_policies", []),
        )


def stage_fuji_precheck(ctx: PipelineContext) -> None:
    """Run FUJI policy pre‑check and merge with existing fuji_dict."""
    fuji_core = (
        _lazy_import("veritas_os.core.fuji", None)
        or _lazy_import("veritas_os.core", "fuji")
    )

    fuji_pre = _build_fail_closed_fuji_precheck("fuji_precheck_missing")
    try:
        if fuji_core is not None and hasattr(fuji_core, "validate_action"):
            fuji_pre = fuji_core.validate_action(ctx.query, ctx.context)  # type: ignore
        elif fuji_core is not None and hasattr(fuji_core, "validate"):
            fuji_pre = fuji_core.validate(ctx.query, ctx.context)  # type: ignore
    except (RuntimeError, ValueError, TypeError, AttributeError) as e:
        _warn(f"[fuji] error (fail-closed): {e}")
        fuji_pre = _build_fail_closed_fuji_precheck("fuji_precheck_error")

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
            fuji_pre["status"] = status_map.get(
                str(fuji_pre.get("status", "rejected")).lower(), "rejected"
            )
    except (KeyError, TypeError, AttributeError):
        if isinstance(fuji_pre, dict):
            fuji_pre["status"] = "rejected"

    ctx.fuji_dict = {
        **(ctx.fuji_dict if isinstance(ctx.fuji_dict, dict) else {}),
        **(fuji_pre if isinstance(fuji_pre, dict) else {}),
    }
    _apply_compiled_policy_runtime_bridge(ctx)

    fuji_status = ctx.fuji_dict.get("status", "allow")
    try:
        risk_val = float(ctx.fuji_dict.get("risk", 0.0))
        if not math.isfinite(risk_val):
            risk_val = 1.0  # fail-closed: NaN/Inf は最大リスクとして扱う
        risk_val = max(0.0, min(1.0, risk_val))
    except (ValueError, TypeError):
        risk_val = 1.0  # fail-closed: 変換不能な値は最大リスクとして扱う
    reasons_list = ctx.fuji_dict.get("reasons", []) or []
    viols = ctx.fuji_dict.get("violations", []) or []

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
        ctx.evidence.append(ev_fuji)


def stage_value_core(
    ctx: PipelineContext,
    *,
    _load_valstats: Any,
    _clip01: Any,
) -> None:
    """Evaluate ValueCore and apply EMA‑based boosts."""
    value_core = (
        _lazy_import("veritas_os.core.value_core", None)
        or _lazy_import("veritas_os.core", "value_core")
    )

    try:
        if value_core is not None and hasattr(value_core, "evaluate"):
            vc = value_core.evaluate(ctx.query, ctx.context or {})  # type: ignore
            ctx.values_payload = {
                "scores": getattr(vc, "scores", {}) if vc is not None else {},
                "total": getattr(vc, "total", 0.0) if vc is not None else 0.0,
                "top_factors": getattr(vc, "top_factors", []) if vc is not None else [],
                "rationale": getattr(vc, "rationale", "") if vc is not None else "",
            }
        else:
            ctx.values_payload = {
                "scores": {},
                "total": 0.0,
                "top_factors": [],
                "rationale": "value_core missing",
            }
    except (RuntimeError, ValueError, TypeError, AttributeError) as e:
        _warn(f"[value_core] evaluation error: {e}")
        ctx.values_payload = {
            "scores": {},
            "total": 0.0,
            "top_factors": [],
            "rationale": "evaluation failed",
        }

    # EMA
    try:
        vs = _load_valstats()
        ctx.value_ema = float(vs.get("ema", 0.5))
        if not math.isfinite(ctx.value_ema):
            ctx.value_ema = 0.5  # fail-safe: NaN/Inf は中立値に戻す
    except (ValueError, TypeError):
        ctx.value_ema = 0.5

    BOOST_MAX = float(os.getenv("VERITAS_VALUE_BOOST_MAX", "0.05"))
    # EMA deviation from neutral (0.5) scaled to [-BOOST_MAX, +BOOST_MAX]
    boost = max(-1.0, min(1.0, (ctx.value_ema - 0.5) * 2.0)) * BOOST_MAX

    ctx.input_alts = _apply_value_boost(ctx.input_alts, boost)
    ctx.alternatives = _apply_value_boost(ctx.alternatives, boost)

    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))
    try:
        ctx.effective_risk = float(ctx.fuji_dict.get("risk", 0.0)) * (
            1.0 - RISK_EMA_WEIGHT * ctx.value_ema
        )
    except (ValueError, TypeError):
        ctx.effective_risk = 0.0
    ctx.effective_risk = max(0.0, min(1.0, ctx.effective_risk))

    TELOS_EMA_DELTA = float(os.getenv("VERITAS_TELOS_EMA_DELTA", "0.10"))
    # Shift telos threshold by EMA deviation: high EMA lowers threshold, low EMA raises it
    ema_deviation = max(-1.0, min(1.0, (ctx.value_ema - 0.5) * 2.0))
    ctx.telos_threshold = BASE_TELOS_THRESHOLD - TELOS_EMA_DELTA * ema_deviation
    ctx.telos_threshold = max(TELOS_THRESHOLD_MIN, min(TELOS_THRESHOLD_MAX, ctx.telos_threshold))

    # world.utility synthesis
    try:
        v_total = _clip01(ctx.values_payload.get("total", 0.5))
        t_val = _clip01(ctx.telos)
        r_val = _clip01(ctx.effective_risk)

        for d in ctx.alternatives:
            if not isinstance(d, dict):
                continue
            base = _clip01(d.get("score", 0.0))
            util = base
            util *= 0.5 + 0.5 * v_total
            util *= 1.0 - r_val
            util *= 0.5 + 0.5 * t_val
            util = _clip01(util)
            d.setdefault("world", {})
            if isinstance(d["world"], dict):
                d["world"]["utility"] = util

        avg_u = (
            (sum(float((d.get("world") or {}).get("utility", 0.0)) for d in ctx.alternatives) / len(ctx.alternatives))
            if ctx.alternatives
            else 0.0
        )
        ctx.response_extras.setdefault("metrics", {})
        if not isinstance(ctx.response_extras["metrics"], dict):
            ctx.response_extras["metrics"] = {}
        ctx.response_extras["metrics"]["avg_world_utility"] = round(float(avg_u), 4)
    except (ValueError, TypeError) as e:
        _warn(f"[world.utility] skipped: {e}")


def stage_gate_decision(ctx: PipelineContext) -> None:
    """Apply gate decision based on FUJI status and risk/telos thresholds."""
    gate_stage_started_at = time.time()
    ctx.decision_status, ctx.rejection_reason = "allow", None
    ctx.modifications = ctx.fuji_dict.get("modifications") or []

    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))

    # merge Debate risk_delta
    try:
        if isinstance(ctx.debate, list) and ctx.debate:
            delta = float((ctx.debate[0] or {}).get("risk_delta", 0.0))
            if delta:
                new_risk = max(0.0, min(1.0, float(ctx.fuji_dict.get("risk", 0.0)) + delta))
                ctx.fuji_dict["risk"] = new_risk
                ctx.effective_risk = max(
                    0.0, min(1.0, new_risk * (1.0 - RISK_EMA_WEIGHT * ctx.value_ema))
                )
    except (ValueError, TypeError) as e:
        _warn(f"[Debate→FUJI] merge failed: {e}")

    if ctx.fuji_dict.get("status") == "modify":
        ctx.modifications = ctx.fuji_dict.get("modifications") or []
    elif ctx.fuji_dict.get("status") == "rejected":
        ctx.decision_status = "rejected"
        ctx.rejection_reason = (
            "FUJI gate: "
            + ", ".join(ctx.fuji_dict.get("reasons", []) or ["policy_violation"])
        )
        ctx.chosen, ctx.alternatives = {}, []
    elif ctx.effective_risk >= HIGH_RISK_THRESHOLD and float(ctx.telos) < float(ctx.telos_threshold):
        ctx.decision_status = "rejected"
        ctx.rejection_reason = (
            f"FUJI gate: high risk ({ctx.effective_risk:.2f}) "
            f"& low telos (<{ctx.telos_threshold:.2f})"
        )
        ctx.chosen, ctx.alternatives = {}, []

    ctx.response_extras["metrics"]["stage_latency"]["gate"] = max(
        0,
        int((time.time() - gate_stage_started_at) * 1000),
    )
