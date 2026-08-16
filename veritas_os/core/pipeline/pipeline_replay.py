# veritas_os/core/pipeline_replay.py
# -*- coding: utf-8 -*-
"""
Pipeline replay / deterministic decision replay.

Functions moved from pipeline.py to isolate replay logic.
"""
from __future__ import annotations

import json
import re
import time
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils import utc_now_iso_z
from veritas_os.replay.canonical_replay import TRUSTED_REPLAY_MARKER
from veritas_os.replay.canonical_replay import ReplayControls, build_replay_evidence
from veritas_os.replay.semantic_profile import semantic_projection


# ★ パストラバーサル防止
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_filename_id(raw_id: str) -> str:
    """Sanitize an ID for safe use in file names (prevent path traversal)."""
    return _SAFE_FILENAME_RE.sub("_", str(raw_id))[:128]


def _sanitize_for_diff(value: Any) -> Any:
    """Normalize payload for deterministic diffing by removing volatile fields."""
    if isinstance(value, dict):
        volatile = {
            "created_at",
            "latency_ms",
            "stage_latency",
            "replay_time_ms",
            "ts",
            "request_id",
            "canonical_decision_artifact",
            "canonical_decision_trust_receipt",
            "canonical_replay_source",
            "canonical_replay_source_receipt",
        }
        return {
            str(k): _sanitize_for_diff(v)
            for k, v in value.items()
            if str(k) not in volatile
        }
    if isinstance(value, list):
        return [_sanitize_for_diff(v) for v in value]
    return value


def _build_replay_diff(
    original: Dict[str, Any],
    replayed: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a concise structural diff report for audit-friendly replay checks."""
    orig_norm = _sanitize_for_diff(original)
    replay_norm = _sanitize_for_diff(replayed)
    if orig_norm == replay_norm:
        return {
            "changed": False,
            "summary": "no_diff",
            "keys": [],
            "severity": "info",
            "divergence_level": "no_divergence",
        }

    keys = sorted(set(orig_norm.keys()) | set(replay_norm.keys()))
    changed_keys = [key for key in keys if orig_norm.get(key) != replay_norm.get(key)]

    _severity_map: Dict[str, str] = {
        "decision": "critical",
        "fuji": "critical",
        "value_scores": "warning",
        "continuation_state": "warning",
        "continuation_receipt": "warning",
    }
    field_severities = [_severity_map.get(k, "info") for k in changed_keys]
    max_severity = (
        "critical" if "critical" in field_severities
        else "warning" if "warning" in field_severities
        else "info"
    )
    divergence = (
        "critical_divergence" if "critical" in field_severities
        else "acceptable_divergence" if field_severities
        else "no_divergence"
    )

    return {
        "changed": True,
        "summary": f"changed_keys={len(changed_keys)}",
        "keys": changed_keys,
        "severity": max_severity,
        "divergence_level": divergence,
        "original": orig_norm,
        "replayed": replay_norm,
    }


def _load_persisted_decision(
    decision_id: str,
    *,
    LOG_DIR: Any,
) -> Optional[Dict[str, Any]]:
    """Load persisted decision snapshot by decision_id/request_id from LOG_DIR."""
    log_dir = Path(LOG_DIR)
    if not log_dir.exists():
        return None
    candidates = sorted(log_dir.glob("decide_*.json"), reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, KeyError):
            continue
        if not isinstance(payload, dict):
            continue
        rid = str(payload.get("request_id") or "")
        did = str(payload.get("decision_id") or "")
        if decision_id in {rid, did}:
            return payload
    return None


class _ReplayRequest:
    """Minimal Request-like object accepted by run_decide_pipeline during replay."""

    def __init__(self, *, mock_external_apis: bool = True) -> None:
        self.query_params: Dict[str, Any] = {}
        self._veritas_replay_marker = TRUSTED_REPLAY_MARKER
        self._veritas_mock_external_apis = mock_external_apis


async def replay_decision(
    decision_id: str,
    *,
    mock_external_apis: bool = True,
    run_decide_pipeline_fn: Any,
    DecideRequest: Any,
    LOG_DIR: Any,
    REPLAY_REPORT_DIR: Any,
    _HAS_ATOMIC_IO: bool = False,
    _atomic_write_json: Any = None,
    _load_decision_fn: Any = None,
    _load_replay_source_fn: Any = None,
) -> Dict[str, Any]:
    """Replay a persisted decision deterministically and generate an audit diff report."""
    started_at = time.time()
    source = (
        _load_replay_source_fn(decision_id)
        if _load_replay_source_fn is not None
        else None
    )
    if source is not None:
        replay_meta = source.deterministic_replay
        source_output = replay_meta.get("final_output")
        snapshot = source_output if isinstance(source_output, dict) else {}
    elif _load_decision_fn is not None:
        snapshot = _load_decision_fn(decision_id)
    else:
        snapshot = _load_persisted_decision(decision_id, LOG_DIR=LOG_DIR)
    if snapshot is None:
        return {
            "match": False,
            "diff": {"error": "decision_not_found", "decision_id": decision_id},
            "replay_time_ms": max(1, int((time.time() - started_at) * 1000)),
        }

    replay_meta = (
        source.deterministic_replay
        if source is not None
        else snapshot.get("deterministic_replay") or {}
    )
    req_body = replay_meta.get("request_body") or {}
    if not isinstance(req_body, dict):
        req_body = {}

    req_body.setdefault("query", snapshot.get("query") or "")
    ctx = req_body.setdefault("context", {})
    if not isinstance(ctx, dict):
        ctx = {}
        req_body["context"] = ctx

    req_body["request_id"] = str(uuid4())
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

    replay_output = await run_decide_pipeline_fn(
        replay_req,
        _ReplayRequest(mock_external_apis=bool(mock_external_apis)),
    )
    original_output = replay_meta.get("final_output") or {}
    if not isinstance(original_output, dict):
        original_output = {}
    diff = _build_replay_diff(
        semantic_projection(original_output),
        semantic_projection(replay_output),
    )
    match = not bool(diff.get("changed"))

    report = {
        "decision_id": str(snapshot.get("request_id") or decision_id),
        "match": match,
        "diff": diff,
        "replay_time_ms": max(1, int((time.time() - started_at) * 1000)),
        "created_at": utc_now_iso_z(),
    }
    if source is not None and isinstance(replay_output, dict):
        controls = ReplayControls(
            strict=bool(mock_external_apis),
            mock_external_apis=bool(mock_external_apis),
            seed=int(req_body.get("seed", 0) or 0),
            temperature=float(req_body.get("temperature", 0) or 0),
        )
        evidence = build_replay_evidence(
            source,
            replay_output,
            controls,
        )
        if (
            evidence.semantic_match != match
            or list(evidence.fields_changed) != diff["keys"]
            or evidence.severity != diff["severity"]
            or evidence.divergence_level != diff["divergence_level"]
        ):
            raise ValueError("canonical replay semantic comparison mismatch")
        report["canonical_replay_evidence"] = evidence.model_dump(mode="json")

    try:
        Path(REPLAY_REPORT_DIR).mkdir(parents=True, exist_ok=True)
        safe_id = _safe_filename_id(report["decision_id"])
        report_path = Path(REPLAY_REPORT_DIR) / f"replay_{safe_id}_{int(time.time() * 1000)}.json"
        if _HAS_ATOMIC_IO and _atomic_write_json is not None:
            _atomic_write_json(report_path, report, indent=2)
        else:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        report["report_path"] = str(report_path)
    except (ValueError, TypeError, OSError) as e:
        report.setdefault("diff", {})
        report["diff"]["report_save_error"] = repr(e)

    return {
        "match": report["match"],
        "diff": report["diff"],
        "replay_time_ms": report["replay_time_ms"],
        "canonical_replay_evidence": report.get("canonical_replay_evidence"),
    }
