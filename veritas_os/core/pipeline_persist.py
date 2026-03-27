# veritas_os/core/pipeline_persist.py
# -*- coding: utf-8 -*-
"""
Pipeline persist / telemetry stage.

Handles:
- Audit log writing
- Decision record persistence to disk
- Memory‑store persistence
- Dataset record writing
- WorldState update + AGI hint
- ReasonOS reflection + meta log
- Replay snapshot building
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pipeline_types import PipelineContext
from .utils import utc_now, utc_now_iso_z, redact_payload
from .pipeline_helpers import _warn

logger = logging.getLogger(__name__)


def _collect_external_dependency_evidence() -> Dict[str, Any]:
    """Collect runtime dependency versions used for replay audit evidence."""
    package_names = (
        "openai",
        "anthropic",
        "httpx",
        "pydantic",
    )
    packages: Dict[str, str] = {}
    for package_name in package_names:
        try:
            packages[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            packages[package_name] = "not_installed"

    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


def _stable_checksum(payload: Any) -> str:
    """Return a deterministic SHA-256 checksum for replay snapshots."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def persist_audit_log(
    ctx: PipelineContext,
    *,
    append_trust_log_fn: Any,
    write_shadow_decide_fn: Any,
) -> None:
    """Write audit / trust log entry (best‑effort).

    The audit entry deliberately excludes bulky nested objects such as
    ``ctx.context`` (which may contain ``world_state``, ``projects``,
    full history arrays, etc.).  Full payloads are persisted separately
    in ``decide_*.json`` and the encrypted ``trust_log.jsonl``.

    Only scalar metadata required for audit-chain verification and
    operational triage is included here.  The ``context_user_id`` field
    preserves the user linkage without embedding the entire context dict.
    """
    try:
        # --- Compact chosen: keep only title/answer, drop nested blobs ---
        chosen_raw = ctx.chosen
        if isinstance(chosen_raw, dict):
            chosen_compact: Any = {
                k: v for k, v in chosen_raw.items()
                if k in {"title", "answer", "action", "status"}
                and isinstance(v, (str, int, float, bool, type(None)))
            }
        else:
            chosen_compact = chosen_raw

        audit_entry = {
            "request_id": ctx.request_id,
            "created_at": utc_now().isoformat(),
            # Only keep the user_id from context — the full context dict
            # (world_state, projects, history, etc.) is excluded from the
            # trust log to prevent entry bloat.
            "context_user_id": (ctx.context or {}).get("user_id"),
            "query": ctx.query,
            "chosen": chosen_compact,
            "telos_score": float(ctx.telos),
            "fuji_status": (ctx.fuji_dict or {}).get("status", "n/a"),
            "fuji_risk": float((ctx.fuji_dict or {}).get("risk", 0.0)),
            "gate_status": (ctx.fuji_dict or {}).get("status", "n/a"),
            "gate_risk": float((ctx.fuji_dict or {}).get("risk", 0.0)),
            "gate_total": float(ctx.values_payload.get("total", 0.0)),
            "plan_steps": (
                len(ctx.plan.get("steps", []))
                if isinstance(ctx.plan, dict)
                else 0
            ),
            "fast_mode": bool(ctx.fast_mode),
            "mem_hits": int(
                (ctx.response_extras.get("metrics") or {}).get("mem_hits", 0) or 0
            ),
            "web_hits": int(
                (ctx.response_extras.get("metrics") or {}).get("web_hits", 0) or 0
            ),
            "critique_ok": (
                bool((ctx.critique or {}).get("ok"))
                if isinstance(ctx.critique, dict)
                else False
            ),
            "critique_mode": (
                (ctx.critique or {}).get("mode")
                if isinstance(ctx.critique, dict)
                else None
            ),
            "critique_reason": (
                (ctx.critique or {}).get("reason")
                if isinstance(ctx.critique, dict)
                else None
            ),
        }
        audit_entry = redact_payload(audit_entry)
        append_trust_log_fn(audit_entry)
        write_shadow_decide_fn(
            ctx.request_id,
            ctx.body,
            ctx.chosen,
            float(ctx.telos),
            ctx.fuji_dict,
        )
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError, KeyError) as e:
        _warn(f"[audit] log write skipped: {repr(e)}")


def persist_to_memory(
    ctx: PipelineContext,
    payload: Dict[str, Any],
    *,
    _get_memory_store: Any,
    _memory_put: Any,
) -> None:
    """Persist decision and episode into MemoryOS (best‑effort)."""
    try:
        store2 = _get_memory_store()
        if store2 is not None:
            decision_key = f"decision_{ctx.request_id}"
            decision_value = redact_payload(
                {
                    "kind": "decision",
                    "request_id": ctx.request_id,
                    "query": ctx.query,
                    "chosen": payload.get("chosen"),
                    "gate": payload.get("gate"),
                    "values": payload.get("values"),
                    "extras": payload.get("extras"),
                    "created_at": utc_now_iso_z(),
                }
            )
            _memory_put(store2, ctx.user_id, key=decision_key, value=decision_value)

            episode_key = f"episode_{time.time_ns()}_{ctx.request_id[:8]}"
            episode_value = redact_payload(
                {
                    "kind": "episode",
                    "request_id": ctx.request_id,
                    "query": ctx.query,
                    "chosen": payload.get("chosen"),
                    "decision_status": payload.get("decision_status"),
                    "rejection_reason": payload.get("rejection_reason"),
                    "created_at": utc_now_iso_z(),
                }
            )
            _memory_put(store2, ctx.user_id, key=episode_key, value=episode_value)
    except (KeyError, TypeError, AttributeError) as e:
        extras_tmp = payload.setdefault("extras", {})
        if isinstance(extras_tmp, dict):
            extras_tmp.setdefault("env_tools", {})
            if isinstance(extras_tmp["env_tools"], dict):
                extras_tmp["env_tools"]["memory_decision_save_error"] = repr(e)


def persist_reason_and_reflection(
    ctx: PipelineContext,
    payload: Dict[str, Any],
    *,
    VAL_JSON: Any,
    META_LOG: Any,
    _load_valstats: Any,
    _save_valstats: Any,
) -> None:
    """ReasonOS: reflection + LLM reason + meta log (best‑effort)."""
    from .pipeline_helpers import _lazy_import

    reason_core = (
        _lazy_import("veritas_os.core.reason", None)
        or _lazy_import("veritas_os.core", "reason")
    )

    try:
        if reason_core is not None and hasattr(reason_core, "reflect"):
            reflection = reason_core.reflect(  # type: ignore
                {
                    "query": ctx.query,
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
            ema2 = max(
                0.0,
                min(1.0, ema2 + float(reflection.get("next_value_boost", 0.0) or 0.0)),
            )
            valstats2["ema"] = round(ema2, 4)
            _save_valstats(valstats2)

            Path(META_LOG).parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "created_at": utc_now_iso_z(),
                "request_id": ctx.request_id,
                "next_value_boost": float(reflection.get("next_value_boost", 0.0) or 0.0),
                "value_ema": ema2,
                "source": "reason_core",
                "fast_mode": bool(ctx.fast_mode),
            }
            with open(META_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (OSError, ValueError, TypeError) as e2:
            _warn(f"[ReasonOS] meta_log append skipped: {e2}")

        llm_stage_started_at = time.time()
        try:
            llm_reason = None
            if reason_core is not None and hasattr(reason_core, "generate_reason"):
                llm_reason = reason_core.generate_reason(  # type: ignore
                    query=ctx.query,
                    planner=payload.get("planner") or payload.get("plan"),
                    values=payload.get("values"),
                    gate=payload.get("gate"),
                    context=ctx.context,
                )

            note_text = ""
            if isinstance(llm_reason, dict):
                note_text = llm_reason.get("text") or ""
            elif isinstance(llm_reason, str):
                note_text = llm_reason

            if not note_text:
                tips = reflection.get("improvement_tips") or []
                note_text = (
                    " / ".join(str(t) for t in tips)
                    if tips
                    else "自動反省メモはありません。"
                )

            payload["reason"] = {
                "note": note_text,
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
                "llm": llm_reason,
            }
            extras_for_llm = payload.setdefault("extras", {})
            if isinstance(extras_for_llm, dict):
                extras_for_llm.setdefault("metrics", {})
                if isinstance(extras_for_llm["metrics"], dict):
                    stage_latency = extras_for_llm["metrics"].setdefault("stage_latency", {})
                    if isinstance(stage_latency, dict):
                        stage_latency["llm"] = max(
                            0, int((time.time() - llm_stage_started_at) * 1000)
                        )
        except Exception as e2:  # reason_core.generate_reason delegates to LLM; may raise LLMError etc.
            _warn(f"[ReasonOS] LLM reason failed: {e2}")
            tips = reflection.get("improvement_tips") or []
            payload["reason"] = {
                "note": " / ".join(tips) if tips else "reflection only.",
                "next_value_boost": reflection.get("next_value_boost", 0.0),
                "reflection": reflection,
            }
            extras_for_llm = payload.setdefault("extras", {})
            if isinstance(extras_for_llm, dict):
                extras_for_llm.setdefault("metrics", {})
                if isinstance(extras_for_llm["metrics"], dict):
                    stage_latency = extras_for_llm["metrics"].setdefault("stage_latency", {})
                    if isinstance(stage_latency, dict):
                        stage_latency["llm"] = max(
                            0, int((time.time() - llm_stage_started_at) * 1000)
                        )
    except Exception as e:  # ReasonOS delegates to LLM subsystems; must not crash decide
        _warn(f"[ReasonOS] final fallback failed: {e}")
        payload["reason"] = {"note": "reflection/LLM both failed"}


def persist_dataset_record(
    ctx: PipelineContext,
    payload: Dict[str, Any],
    *,
    duration_ms: int,
    build_dataset_record_fn: Any,
    append_dataset_record_fn: Any,
) -> None:
    """Write dataset record (best‑effort)."""
    try:
        duration_ms_ds = int(
            (payload.get("extras") or {}).get("metrics", {}).get("latency_ms", 0)
            or duration_ms
        )
        duration_ms_ds = max(1, duration_ms_ds)

        meta_ds = {
            "session_id": (ctx.context or {}).get("user_id") or "anon",
            "request_id": ctx.request_id,
            "model": os.getenv("VERITAS_MODEL_NAME", "gpt-5-thinking"),
            "api_version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
            "kernel_version": os.getenv("VERITAS_KERNEL_VERSION", "core-kernel 0.x"),
            "latency_ms": duration_ms_ds,
            "fast_mode": bool(ctx.fast_mode),
        }
        eval_meta = {
            "task_type": "decision",
            "policy_tags": ["no_harm", "privacy_ok"],
            "rater": {"type": "ai", "id": "telos-proxy"},
        }
        append_dataset_record_fn(
            build_dataset_record_fn(
                req_payload=ctx.body,
                res_payload=payload,
                meta=meta_ds,
                eval_meta=eval_meta,
            )
        )
    except (OSError, RuntimeError, TypeError, ValueError, AttributeError, KeyError) as e:
        _warn(f"[dataset] skip: {e}")


def persist_decision_to_disk(
    ctx: PipelineContext,
    payload: Dict[str, Any],
    *,
    duration_ms: int,
    LOG_DIR: Any,
    DATASET_DIR: Any,
    _HAS_ATOMIC_IO: bool,
    _atomic_write_json: Any,
) -> None:
    """Write decision record to disk (best‑effort)."""
    persist_stage_started_at = time.time()
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        Path(DATASET_DIR).mkdir(parents=True, exist_ok=True)

        metrics2 = (payload.get("extras") or {}).get("metrics") or {}
        latency_ms2 = int(metrics2.get("latency_ms", duration_ms))

        evidence_list: List[Dict[str, Any]] = []
        if isinstance(payload.get("evidence"), list):
            evidence_list = [ev for ev in payload["evidence"] if isinstance(ev, dict)]

        actual_mem_evidence_count = 0
        for ev in evidence_list:
            src = str(ev.get("source", "")).lower()
            if src.startswith("memory"):
                actual_mem_evidence_count += 1

        meta_payload = payload.get("meta") or {}
        if not isinstance(meta_payload, dict):
            meta_payload = {}

        meta_payload["memory_evidence_count"] = int(
            metrics2.get("memory_evidence_count", 0) or 0
        )
        meta_payload["mem_evidence_count"] = int(actual_mem_evidence_count)
        meta_payload["mem_hits"] = int(metrics2.get("mem_hits", 0) or 0)
        meta_payload["web_hits"] = int(metrics2.get("web_hits", 0) or 0)
        meta_payload["fast_mode"] = bool(
            (payload.get("extras") or {}).get("fast_mode", ctx.fast_mode)
        )
        payload["meta"] = meta_payload

        fuji_full = payload.get("fuji") or {}
        world_snapshot = (ctx.context or {}).get("world")

        persist = redact_payload(
            {
                "request_id": ctx.request_id,
                "ts": utc_now_iso_z(timespec="seconds"),
                "query": ctx.query,
                "chosen": payload.get("chosen"),
                "decision_status": payload.get("decision_status") or "unknown",
                "telos_score": float(payload.get("telos_score", 0.0)),
                "gate_risk": float(
                    (
                        (payload.get("gate") or {})
                        if isinstance(payload.get("gate"), dict)
                        else {}
                    ).get("risk", 0.0)
                ),
                "fuji_status": fuji_full.get("status") if isinstance(fuji_full, dict) else None,
                "fuji": fuji_full,
                "latency_ms": latency_ms2,
                "evidence": evidence_list[-5:] if evidence_list else [],
                "memory_evidence_count": int(meta_payload.get("memory_evidence_count", 0) or 0),
                "mem_evidence_count": int(meta_payload.get("mem_evidence_count", 0) or 0),
                "context": ctx.context,
                "world": world_snapshot,
                "fast_mode": bool(
                    (payload.get("extras") or {}).get("fast_mode", ctx.fast_mode)
                ),
                "mem_hits": int(metrics2.get("mem_hits", 0) or 0),
                "web_hits": int(metrics2.get("web_hits", 0) or 0),
                "critique_ok": (
                    bool((ctx.critique or {}).get("ok"))
                    if isinstance(ctx.critique, dict)
                    else False
                ),
                "critique_mode": (
                    (ctx.critique or {}).get("mode")
                    if isinstance(ctx.critique, dict)
                    else None
                ),
                "critique_reason": (
                    (ctx.critique or {}).get("reason")
                    if isinstance(ctx.critique, dict)
                    else None
                ),
            }
        )

        stamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fname = f"decide_{stamp}.json"
        log_path = Path(LOG_DIR) / fname
        dataset_path = Path(DATASET_DIR) / fname
        if _HAS_ATOMIC_IO and _atomic_write_json is not None:
            _atomic_write_json(log_path, persist, indent=2)
            _atomic_write_json(dataset_path, persist)
        else:
            log_path.write_text(
                json.dumps(persist, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            dataset_path.write_text(
                json.dumps(persist, ensure_ascii=False), encoding="utf-8"
            )
    except OSError as e:
        _warn(f"[persist] decide record skipped: {e}")
    finally:
        extras_for_persist = payload.setdefault("extras", {})
        if isinstance(extras_for_persist, dict):
            extras_for_persist.setdefault("metrics", {})
            if isinstance(extras_for_persist["metrics"], dict):
                stage_latency = extras_for_persist["metrics"].setdefault("stage_latency", {})
                if isinstance(stage_latency, dict):
                    stage_latency["persist"] = max(
                        0, int((time.time() - persist_stage_started_at) * 1000)
                    )


def persist_world_state(
    ctx: PipelineContext,
    payload: Dict[str, Any],
) -> None:
    """Update WorldState + AGI hint (best‑effort)."""
    from .pipeline_helpers import _lazy_import

    world_model = (
        _lazy_import("veritas_os.core.world", None)
        or _lazy_import("veritas_os.core.world_model", None)
    )

    try:
        if world_model is not None and hasattr(world_model, "update_from_decision"):
            uid_world = (ctx.context or {}).get("user_id") or ctx.user_id or "anon"
            uid_world = str(uid_world) if uid_world is not None else "anon"

            extras_w = payload.get("extras") or {}
            planner_obj = extras_w.get("planner") if isinstance(extras_w, dict) else None
            latency_ms3 = (
                (extras_w.get("metrics") or {}).get("latency_ms")
                if isinstance(extras_w, dict)
                else None
            )

            world_model.update_from_decision(  # type: ignore
                user_id=uid_world,
                query=payload.get("query") or ctx.query,
                chosen=payload.get("chosen") or {},
                gate=payload.get("gate") or {},
                values=payload.get("values") or {},
                planner=planner_obj if isinstance(planner_obj, dict) else None,
                latency_ms=int(latency_ms3) if isinstance(latency_ms3, (int, float)) else None,
            )
            _warn(f"[WorldModel] state updated for {uid_world}")
    except Exception as e:  # world_model.update may raise arbitrary subsystem errors
        _warn(f"[WorldModel] update_from_decision skipped: {e}")

    # AGI hint
    try:
        if world_model is not None and hasattr(world_model, "next_hint_for_veritas_agi"):
            agi_info = world_model.next_hint_for_veritas_agi()  # type: ignore
            extras2 = payload.setdefault("extras", {})
            if isinstance(extras2, dict):
                extras2["veritas_agi"] = agi_info
    except Exception as e:  # world_model hint may raise arbitrary subsystem errors
        _warn(f"[WorldModel] next_hint_for_veritas_agi skipped: {e}")


def build_replay_snapshot(
    ctx: PipelineContext,
    payload: Dict[str, Any],
    *,
    should_run_web: bool,
) -> None:
    """Build and attach the deterministic replay snapshot to *payload*."""
    payload_for_replay = dict(payload)
    payload_for_replay.pop("deterministic_replay", None)

    evidence_snapshot = (
        payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    )
    retrieval_snapshot = {
        "retrieved": ctx.retrieved if isinstance(ctx.retrieved, list) else [],
        "web": ctx.response_extras.get("web_search"),
    }

    replay_snapshot = {
        "input_prompt": ctx.query,
        "evidence_snapshot": evidence_snapshot,
        "retrieval_snapshot": retrieval_snapshot,
        "retrieval_snapshot_checksum": _stable_checksum(retrieval_snapshot),
        "policy_snapshot": {
            "min_evidence": ctx.min_ev,
            "fast_mode": ctx.fast_mode,
            "mock_external_apis": ctx.mock_external_apis,
        },
        "model_version": os.getenv("VERITAS_MODEL_NAME", "gpt-5-thinking"),
        "temperature": ctx.body.get("temperature", 0),
        "seed": ctx.seed,
        "tool_calls": {
            "memory_search": bool(ctx.query and ctx.retrieved),
            "web_search": bool(should_run_web and not ctx.mock_external_apis),
            "web_search_mocked": bool(should_run_web and ctx.mock_external_apis),
        },
        "external_dependency_versions": _collect_external_dependency_evidence(),
        "stage_outputs": {
            "planner": ctx.response_extras.get("planner"),
            "retrieval": ctx.retrieved,
            "web": ctx.response_extras.get("web_search"),
            "kernel_raw": ctx.raw,
            "fuji": ctx.fuji_dict,
            "gate": payload.get("gate"),
            "values": payload.get("values"),
            "reason": payload.get("reason"),
        },
        "request_body": ctx.body,
        "final_output": payload_for_replay,
    }
    payload["deterministic_replay"] = replay_snapshot
    if isinstance(payload.get("meta"), dict):
        payload["meta"]["replay_ready"] = True
