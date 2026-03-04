"""Decision replay engine for deterministic reproducibility checks."""

from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List

from veritas_os.api.schemas import DecideRequest
from veritas_os.core import pipeline


@dataclass(frozen=True)
class ReplayResult:
    """Replay execution result used by API and compliance reports."""

    decision_id: str
    replay_path: str
    replay_time_ms: int
    strict: bool
    match: bool
    diff: Dict[str, Any]
    diff_summary: str


def _strict_mode_enabled() -> bool:
    raw = (os.getenv("VERITAS_REPLAY_STRICT") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _pipeline_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            text=True,
        )
        version = out.strip()
        if version:
            return version
    except Exception:
        return "unknown"
    return "unknown"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _replay_file_name(decision_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"replay_{decision_id}_{stamp}.json"


def _sort_evidence(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _key(item: Dict[str, Any]) -> str:
        return str(
            item.get("id")
            or item.get("title")
            or item.get("url")
            or item.get("uri")
            or item.get("source")
            or ""
        ).lower()

    return sorted(items, key=_key)


def _normalized_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract stable fields for replay comparison."""
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    fuji = payload.get("fuji") if isinstance(payload.get("fuji"), dict) else {}
    extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}

    decision_output = decision.get("output")
    decision_answer = decision.get("answer")
    fuji_result = fuji.get("result")
    value_scores = payload.get("value_scores")
    evidence = payload.get("evidence")

    if not isinstance(evidence, list):
        evidence = extras.get("evidence") if isinstance(extras.get("evidence"), list) else []

    stable_evidence = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        stable_evidence.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "url": item.get("url") or item.get("uri"),
                "source": item.get("source"),
                "snippet": item.get("snippet"),
            }
        )

    return {
        "decision": {
            "output": decision_output,
            "answer": decision_answer,
        },
        "fuji": {
            "result": fuji_result,
            "status": fuji.get("status"),
        },
        "value_scores": value_scores,
        "evidence": _sort_evidence(stable_evidence),
    }


def _build_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    fields_changed: List[str] = []
    high_level: List[str] = []

    for key in sorted(set(before.keys()) | set(after.keys())):
        if before.get(key) != after.get(key):
            fields_changed.append(key)

    if "decision" in fields_changed:
        high_level.append("Decision output differs.")
    if "fuji" in fields_changed:
        high_level.append("Fuji result differs.")
    if "value_scores" in fields_changed:
        high_level.append("Value scores differ.")
    if "evidence" in fields_changed:
        high_level.append("Evidence set differs.")
    if not high_level:
        high_level.append("No high-level differences.")

    return {
        "high_level": high_level,
        "fields_changed": fields_changed,
        "before": before,
        "after": after,
    }


def _diff_summary(diff: Dict[str, Any]) -> str:
    changed = diff.get("fields_changed") or []
    if not changed:
        return "no_diff"
    return f"fields_changed={','.join(str(v) for v in changed)}"


@contextmanager
def _strict_tool_lock() -> Iterator[None]:
    """Disable external retrieval side-effects for strict replay mode."""
    original_get_memory_store = pipeline._get_memory_store
    try:
        pipeline._get_memory_store = lambda: None
        yield
    finally:
        pipeline._get_memory_store = original_get_memory_store


async def run_replay(decision_id: str, strict: bool | None = None) -> ReplayResult:
    """Replay a persisted decision with deterministic controls and save a report."""
    started = time.time()
    strict_mode = _strict_mode_enabled() if strict is None else bool(strict)

    snapshot = pipeline._load_persisted_decision(decision_id)
    if snapshot is None:
        raise ValueError(f"decision_not_found: {decision_id}")

    replay_meta = snapshot.get("deterministic_replay") if isinstance(snapshot.get("deterministic_replay"), dict) else {}
    req_body = replay_meta.get("request_body") if isinstance(replay_meta.get("request_body"), dict) else {}
    req_body = dict(req_body)

    req_body.setdefault("query", snapshot.get("query") or "")
    context = req_body.get("context") if isinstance(req_body.get("context"), dict) else {}
    req_body["context"] = dict(context)
    req_body["context"]["_replay_mode"] = True
    req_body["context"]["_mock_external_apis"] = strict_mode

    if strict_mode:
        req_body["temperature"] = 0
        req_body["seed"] = int(replay_meta.get("seed", req_body.get("seed", 0)) or 0)
    else:
        req_body.setdefault("temperature", replay_meta.get("temperature", 0))
        req_body.setdefault("seed", replay_meta.get("seed", 0))

    req_body["request_id"] = str(snapshot.get("request_id") or decision_id)

    replay_req = DecideRequest.model_validate(req_body)

    if strict_mode:
        with _strict_tool_lock():
            replay_output = await pipeline.run_decide_pipeline(replay_req, pipeline._ReplayRequest())
    else:
        replay_output = await pipeline.run_decide_pipeline(replay_req, pipeline._ReplayRequest())

    original_output = replay_meta.get("final_output") if isinstance(replay_meta.get("final_output"), dict) else snapshot
    before = _normalized_payload(original_output)
    after = _normalized_payload(replay_output if isinstance(replay_output, dict) else {})
    diff = _build_diff(before, after)
    match = not bool(diff["fields_changed"])

    replay_time_ms = max(1, int((time.time() - started) * 1000))

    report_payload: Dict[str, Any] = {
        "decision_id": str(snapshot.get("request_id") or decision_id),
        "replay_time_ms": replay_time_ms,
        "strict": strict_mode,
        "match": match,
        "diff": diff,
        "meta": {
            "created_at": _iso_now(),
            "pipeline_version": _pipeline_version(),
            "notes": "strict mode reuses deterministic replay snapshot and disables external tools.",
        },
    }

    pipeline.REPLAY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = pipeline.REPLAY_REPORT_DIR / _replay_file_name(str(snapshot.get("request_id") or decision_id))
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return ReplayResult(
        decision_id=str(snapshot.get("request_id") or decision_id),
        replay_path=str(report_path),
        replay_time_ms=replay_time_ms,
        strict=strict_mode,
        match=match,
        diff=diff,
        diff_summary=_diff_summary(diff),
    )

