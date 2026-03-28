"""Decision replay engine for deterministic reproducibility checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from veritas_os.api.schemas import DecideRequest
from veritas_os.core import pipeline

# ★ パストラバーサル防止: ファイル名に使用する ID から危険文字を除去
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")

# ── Replay artifact schema version ──────────────────────────────────
# Bump when the replay report JSON structure changes so that downstream
# audit tooling can detect and handle schema evolution.
REPLAY_SCHEMA_VERSION = "1.0.0"

# ── Diff severity constants ─────────────────────────────────────────
SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# ── Divergence level constants ──────────────────────────────────────
DIVERGENCE_NONE = "no_divergence"
DIVERGENCE_ACCEPTABLE = "acceptable_divergence"
DIVERGENCE_CRITICAL = "critical_divergence"

# Per-field severity mapping.  Fields not listed default to ``info``.
_FIELD_SEVERITY: Dict[str, str] = {
    "decision": SEVERITY_CRITICAL,
    "fuji": SEVERITY_CRITICAL,
    "value_scores": SEVERITY_WARNING,
    "evidence": SEVERITY_INFO,
    # Continuation runtime (shadow/observe) — divergence is warning-level
    # because phase-1 is non-enforcing; critical would be premature.
    "continuation_state": SEVERITY_WARNING,
    "continuation_receipt": SEVERITY_WARNING,
}


def _classify_field_severity(field_name: str) -> str:
    """Return the audit severity level for a changed replay diff field."""
    return _FIELD_SEVERITY.get(field_name, SEVERITY_INFO)


def _determine_divergence(field_severities: List[str]) -> str:
    """Derive overall divergence level from individual field severities."""
    if not field_severities:
        return DIVERGENCE_NONE
    if SEVERITY_CRITICAL in field_severities:
        return DIVERGENCE_CRITICAL
    return DIVERGENCE_ACCEPTABLE


def _safe_filename_id(raw_id: str) -> str:
    """Sanitize an ID for safe use in file names (prevent path traversal)."""
    return _SAFE_FILENAME_RE.sub("_", str(raw_id))[:128]


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
    # ── New audit-quality fields (backward-compatible defaults) ──────
    schema_version: str = REPLAY_SCHEMA_VERSION
    severity: str = SEVERITY_INFO
    divergence_level: str = DIVERGENCE_NONE
    audit_summary: str = ""


def _strict_mode_enabled() -> bool:
    raw = (os.getenv("VERITAS_REPLAY_STRICT") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _pipeline_version() -> str:
    """Return the current git short SHA when available.

    Security note:
        We intentionally do not swallow arbitrary exceptions here so that
        unexpected runtime errors are surfaced during diagnostics.

    Operational note:
        CI can inject ``VERITAS_PIPELINE_VERSION`` to avoid ``unknown`` when
        Git metadata is unavailable in runtime environments.
    """
    injected_version = (os.getenv("VERITAS_PIPELINE_VERSION") or "").strip()
    if injected_version:
        return injected_version

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            text=True,
        )
        version = out.strip()
        if version:
            return version
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"
    return "unknown"


def _is_model_version_enforcement_enabled() -> bool:
    """Return whether replay must enforce snapshot model/version constraints."""
    raw = (os.getenv("VERITAS_REPLAY_ENFORCE_MODEL_VERSION") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _assert_model_version(snapshot_model: str | None) -> None:
    """Raise ValueError when current configured model differs from snapshot."""
    if not _is_model_version_enforcement_enabled():
        return
    expected = (snapshot_model or "").strip()
    require_declared = (
        (os.getenv("VERITAS_REPLAY_REQUIRE_MODEL_VERSION") or "1").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if not expected:
        if require_declared:
            raise ValueError("replay_model_version_missing")
        return

    current = (
        os.getenv("VERITAS_MODEL_NAME")
        or os.getenv("LLM_MODEL")
        or ""
    ).strip()
    if current and current != expected:
        raise ValueError(f"replay_model_version_mismatch: expected={expected} current={current}")

def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _replay_file_name(decision_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_id = _safe_filename_id(decision_id)
    return f"replay_{safe_id}_{stamp}.json"


def _stable_checksum(payload: Any) -> str:
    """Return deterministic SHA-256 over canonicalized payload."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_external_dependency_evidence(value: Any) -> Dict[str, Any]:
    """Return a sanitized dependency evidence map for replay reporting."""
    if not isinstance(value, dict):
        return {}

    packages = value.get("packages") if isinstance(value.get("packages"), dict) else {}
    normalized_packages = {
        str(name): str(version)
        for name, version in packages.items()
    }

    normalized = {
        "python_version": str(value.get("python_version") or ""),
        "platform": str(value.get("platform") or ""),
        "packages": normalized_packages,
    }
    return normalized


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

    # ── Continuation runtime (shadow/observe) ──────────────────────
    # Extract concise continuation fields for replay comparison.
    # When continuation is absent (flag off), these keys are omitted
    # entirely so that replay diffs remain clean.
    continuation_block = payload.get("continuation") if isinstance(payload.get("continuation"), dict) else None
    result: Dict[str, Any] = {
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
    if continuation_block is not None:
        c_state = continuation_block.get("state") if isinstance(continuation_block.get("state"), dict) else {}
        c_receipt = continuation_block.get("receipt") if isinstance(continuation_block.get("receipt"), dict) else {}
        result["continuation_state"] = {
            "claim_lineage_id": c_state.get("claim_lineage_id"),
            "claim_status": c_state.get("claim_status"),
            "law_version": c_state.get("law_version"),
            "snapshot_id": c_state.get("snapshot_id"),
        }
        result["continuation_receipt"] = {
            "receipt_id": c_receipt.get("receipt_id"),
            "revalidation_status": c_receipt.get("revalidation_status"),
            "revalidation_outcome": c_receipt.get("revalidation_outcome"),
            "divergence_flag": c_receipt.get("divergence_flag"),
            "should_refuse_before_effect": c_receipt.get("should_refuse_before_effect"),
            "reason_codes": c_receipt.get("revalidation_reason_codes"),
        }
    return result


def _build_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    fields_changed: List[str] = []
    high_level: List[str] = []
    field_details: List[Dict[str, Any]] = []

    for key in sorted(set(before.keys()) | set(after.keys())):
        if before.get(key) != after.get(key):
            fields_changed.append(key)
            severity = _classify_field_severity(key)
            field_details.append({
                "field": key,
                "severity": severity,
                "before": before.get(key),
                "after": after.get(key),
            })

    if "decision" in fields_changed:
        high_level.append("Decision output differs.")
    if "fuji" in fields_changed:
        high_level.append("Fuji result differs.")
    if "value_scores" in fields_changed:
        high_level.append("Value scores differ.")
    if "evidence" in fields_changed:
        high_level.append("Evidence set differs.")
    if "continuation_state" in fields_changed or "continuation_receipt" in fields_changed:
        high_level.append("Continuation standing differs.")
    if not high_level:
        high_level.append("No high-level differences.")

    field_severities = [d["severity"] for d in field_details]
    divergence = _determine_divergence(field_severities)
    max_severity = (
        SEVERITY_CRITICAL if SEVERITY_CRITICAL in field_severities
        else SEVERITY_WARNING if SEVERITY_WARNING in field_severities
        else SEVERITY_INFO if field_severities
        else SEVERITY_INFO
    )

    return {
        "high_level": high_level,
        "fields_changed": fields_changed,
        "field_details": field_details,
        "max_severity": max_severity,
        "divergence_level": divergence,
        "before": before,
        "after": after,
    }


def _diff_summary(diff: Dict[str, Any]) -> str:
    changed = diff.get("fields_changed") or []
    if not changed:
        return "no_diff"
    return f"fields_changed={','.join(str(v) for v in changed)}"


def _audit_summary(
    *,
    decision_id: str,
    match: bool,
    strict: bool,
    diff: Dict[str, Any],
) -> str:
    """Build a human-readable audit summary for the replay report.

    Example outputs::

        Replay dec-123 (strict): MATCH — no divergence detected.
        Replay dec-456: MISMATCH (critical) — Decision output differs. Fuji result differs.
    """
    mode_label = "strict" if strict else "standard"
    verdict = "MATCH" if match else "MISMATCH"

    if match:
        return f"Replay {decision_id} ({mode_label}): {verdict} — no divergence detected."

    severity_tag = diff.get("max_severity", SEVERITY_INFO)
    details = " ".join(diff.get("high_level") or [])
    return f"Replay {decision_id} ({mode_label}): {verdict} ({severity_tag}) — {details}".rstrip()


def _noop_memory_store() -> None:
    """Return None to disable memory store during strict replay."""
    return None


async def run_replay(decision_id: str, strict: bool | None = None) -> ReplayResult:
    """Replay a persisted decision with deterministic controls and save a report."""
    started = time.time()
    strict_mode = _strict_mode_enabled() if strict is None else bool(strict)

    snapshot = pipeline._load_persisted_decision(decision_id)
    if snapshot is None:
        raise ValueError(f"decision_not_found: {decision_id}")

    replay_meta = snapshot.get("deterministic_replay") if isinstance(snapshot.get("deterministic_replay"), dict) else {}
    _assert_model_version(replay_meta.get("model_version"))

    expected_retrieval_checksum = replay_meta.get("retrieval_snapshot_checksum")
    if expected_retrieval_checksum:
        retrieval_snapshot = replay_meta.get("retrieval_snapshot") if isinstance(replay_meta.get("retrieval_snapshot"), dict) else {}
        actual_retrieval_checksum = _stable_checksum(retrieval_snapshot)
        if str(expected_retrieval_checksum) != actual_retrieval_checksum:
            raise ValueError("replay_retrieval_snapshot_checksum_mismatch")

    replay_dependency_evidence = _normalize_external_dependency_evidence(
        replay_meta.get("external_dependency_versions")
    )

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

    replay_kwargs: Dict[str, Any] = {}
    if strict_mode:
        replay_kwargs["memory_store_getter"] = _noop_memory_store
    replay_output = await pipeline.run_decide_pipeline(
        replay_req, pipeline._ReplayRequest(), **replay_kwargs
    )

    original_output = replay_meta.get("final_output") if isinstance(replay_meta.get("final_output"), dict) else snapshot
    before = _normalized_payload(original_output)
    after = _normalized_payload(replay_output if isinstance(replay_output, dict) else {})
    diff = _build_diff(before, after)
    match = not bool(diff["fields_changed"])

    replay_time_ms = max(1, int((time.time() - started) * 1000))

    resolved_id = str(snapshot.get("request_id") or decision_id)
    max_severity = diff.get("max_severity", SEVERITY_INFO)
    divergence = diff.get("divergence_level", DIVERGENCE_NONE)
    summary = _audit_summary(
        decision_id=resolved_id,
        match=match,
        strict=strict_mode,
        diff=diff,
    )

    report_payload: Dict[str, Any] = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "decision_id": resolved_id,
        "replay_time_ms": replay_time_ms,
        "strict": strict_mode,
        "match": match,
        "severity": max_severity,
        "divergence_level": divergence,
        "audit_summary": summary,
        "diff": diff,
        "meta": {
            "created_at": _iso_now(),
            "pipeline_version": _pipeline_version(),
            "notes": "strict mode reuses deterministic replay snapshot and disables external tools.",
            "external_dependency_versions": replay_dependency_evidence,
        },
    }

    pipeline.REPLAY_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = pipeline.REPLAY_REPORT_DIR / _replay_file_name(resolved_id)
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return ReplayResult(
        decision_id=resolved_id,
        replay_path=str(report_path),
        replay_time_ms=replay_time_ms,
        strict=strict_mode,
        match=match,
        diff=diff,
        diff_summary=_diff_summary(diff),
        schema_version=REPLAY_SCHEMA_VERSION,
        severity=max_severity,
        divergence_level=divergence,
        audit_summary=summary,
    )
