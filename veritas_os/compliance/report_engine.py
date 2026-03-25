"""Compliance report engine for enterprise-grade audit exports.

Generates reproducible, cryptographically signed compliance reports that
integrate decision logs, replay verification, trustlog integrity checks,
and governance policy context.  Every report carries an ``evidence_completeness``
score and ``input_sources`` block so auditors can trace each claim to its
source artifact.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json

from veritas_os.audit.trustlog_signed import (
    PRIVATE_KEY_PATH,
    PUBLIC_KEY_PATH,
    store_keypair,
    verify_trustlog_chain,
)
from veritas_os.core.pipeline import LOG_DIR, REPLAY_REPORT_DIR
from veritas_os.logging.trust_log import verify_trust_log
from veritas_os.reporting.exporters import persist_report_json, persist_report_pdf
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.security.signing import sign_payload_hash

logger = logging.getLogger(__name__)

REPORT_SCHEMA_VERSION = "1.2.0"

REPORT_DIR = (Path(LOG_DIR) / "compliance_reports").resolve()

# ★ パストラバーサル防止: ファイル名に使用する ID から危険文字を除去
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_\-]")

# Default risk thresholds used when governance policy is unavailable.
_DEFAULT_RISK_THRESHOLDS = {
    "medium_lower": 0.3,
    "high_lower": 0.5,
    "critical_lower": 0.8,
}


def _safe_filename_id(raw_id: str) -> str:
    """Sanitize an ID for safe use in file names (prevent path traversal)."""
    return _SAFE_FILENAME_RE.sub("_", str(raw_id))[:128]


# ---------- governance policy integration ----------

def _load_governance_context() -> Dict[str, Any]:
    """Load governance policy for risk thresholds and metadata.

    Returns a dict with ``risk_thresholds``, ``policy_version``, and
    ``policy_available`` so callers can degrade gracefully when the
    governance module is unreachable.
    """
    try:
        from veritas_os.api.governance import get_policy
        policy = get_policy()
        rt = policy.get("risk_thresholds", {})
        return {
            "policy_available": True,
            "policy_version": policy.get("version", "unknown"),
            "policy_updated_at": policy.get("updated_at", ""),
            "risk_thresholds": {
                "medium_lower": float(rt.get("allow_upper", _DEFAULT_RISK_THRESHOLDS["medium_lower"])),
                "high_lower": float(rt.get("warn_upper", _DEFAULT_RISK_THRESHOLDS["high_lower"])),
                "critical_lower": float(rt.get("human_review_upper", _DEFAULT_RISK_THRESHOLDS["critical_lower"])),
            },
        }
    except Exception as exc:
        logger.warning("Governance policy unavailable, using defaults: %s", exc)
        return {
            "policy_available": False,
            "policy_version": "unavailable",
            "policy_updated_at": "",
            "risk_thresholds": dict(_DEFAULT_RISK_THRESHOLDS),
        }


# ---------- input validation ----------

_DECISION_REQUIRED_FIELDS = ("request_id",)

_KNOWN_DECISION_STATUSES = frozenset(
    {"allow", "reject", "rejected", "review", "block", "escalate"}
)


def _validate_timestamp(raw: str) -> Optional[str]:
    """Return an issue string if *raw* is not a valid ISO-8601 timestamp, else ``None``."""
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "invalid_timestamp_format"
    return None


def _validate_decision_record(rec: Dict[str, Any]) -> List[str]:
    """Validate a decision record and return a list of issues (empty = valid).

    Checks for required fields, correct types for known fields, and
    structural consistency of nested sections.
    """
    issues: List[str] = []

    for field in _DECISION_REQUIRED_FIELDS:
        if not rec.get(field):
            issues.append(f"missing_required_field:{field}")

    gate = rec.get("gate")
    if gate is not None and not isinstance(gate, dict):
        issues.append("invalid_gate_type:expected_dict")

    fuji = rec.get("fuji")
    if fuji is not None and not isinstance(fuji, dict):
        issues.append("invalid_fuji_type:expected_dict")

    if isinstance(gate, dict):
        risk_raw = gate.get("risk")
        if risk_raw is not None:
            try:
                risk_val = float(risk_raw)
                if not (0.0 <= risk_val <= 1.0):
                    issues.append("risk_out_of_range:expected_0_to_1")
            except (TypeError, ValueError):
                issues.append("risk_not_numeric")

    # Validate timestamp when present.
    ts_raw = rec.get("ts") or rec.get("created_at")
    if ts_raw is not None:
        ts_issue = _validate_timestamp(str(ts_raw))
        if ts_issue:
            issues.append(ts_issue)

    # Warn on unknown decision_status values.
    status = rec.get("decision_status")
    if status is not None and status not in _KNOWN_DECISION_STATUSES:
        issues.append(f"unknown_decision_status:{status}")

    return issues


_REPLAY_REQUIRED_FIELDS = ("match", "diff")


def _validate_replay_payload(payload: Any) -> Dict[str, Any]:
    """Validate and normalize a raw replay JSON payload.

    Returns a dict with ``available``, ``valid``, and either the
    validated fields or a ``reason`` describing the issue.
    """
    if not isinstance(payload, dict):
        return {"available": False, "valid": False, "reason": "invalid_type"}

    # Check required fields.
    missing = [f for f in _REPLAY_REQUIRED_FIELDS if f not in payload]
    if missing:
        return {
            "available": True,
            "valid": False,
            "reason": f"missing_required_fields:{','.join(missing)}",
        }

    result: Dict[str, Any] = {
        "available": True,
        "valid": True,
        "match": bool(payload.get("match")),
        "diff": payload.get("diff", {}),
        "replay_time_ms": payload.get("replay_time_ms"),
    }

    # Validate schema_version if present
    sv = payload.get("schema_version")
    if sv is not None:
        result["schema_version"] = str(sv)

    # Validate severity / divergence_level if present
    for field in ("severity", "divergence_level", "audit_summary"):
        val = payload.get(field)
        if val is not None:
            result[field] = str(val)

    return result


@dataclass(frozen=True)
class ReportArtifact:
    """Container for generated report payload and persisted artifacts."""

    report: Dict[str, Any]
    json_path: Path
    pdf_path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _iter_decision_logs() -> Iterable[Dict[str, Any]]:
    log_dir = Path(LOG_DIR)
    if not log_dir.exists():
        return []

    records: List[Dict[str, Any]] = []
    for path in sorted(log_dir.glob("decide_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable decision log %s: %s", path, exc)
            continue
        if isinstance(payload, dict):
            payload["_source_path"] = str(path)
            records.append(payload)
        else:
            logger.warning("Skipping non-dict decision log %s", path)
    return records


def _find_decision(decision_id: str) -> Optional[Dict[str, Any]]:
    for rec in _iter_decision_logs():
        rid = str(rec.get("request_id") or "")
        did = str(rec.get("decision_id") or "")
        if decision_id in {rid, did}:
            return rec
    return None


def _classify_risk(
    score: float,
    thresholds: Optional[Dict[str, float]] = None,
) -> str:
    t = thresholds or _DEFAULT_RISK_THRESHOLDS
    if score >= t.get("critical_lower", 0.8):
        return "critical"
    if score >= t.get("high_lower", 0.5):
        return "high"
    if score >= t.get("medium_lower", 0.3):
        return "medium"
    return "low"


def _latest_replay_result(decision_id: str) -> Dict[str, Any]:
    replay_dir = Path(REPLAY_REPORT_DIR)
    if not replay_dir.exists():
        return {"available": False, "result": "missing"}

    safe_id = _safe_filename_id(decision_id)
    candidates = sorted(replay_dir.glob(f"replay_{safe_id}_*.json"), reverse=True)
    if not candidates:
        return {"available": False, "result": "missing"}

    try:
        payload = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "result": "unreadable"}

    validated = _validate_replay_payload(payload)
    if not validated.get("valid"):
        return {"available": False, "result": validated.get("reason", "invalid")}

    validated["source"] = str(candidates[0])
    return validated


def _build_decision_section(
    rec: Dict[str, Any],
    gov_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    validation_issues = _validate_decision_record(rec)

    gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
    fuji = rec.get("fuji") if isinstance(rec.get("fuji"), dict) else {}
    risk_score = float(gate.get("risk", rec.get("gate_risk", 0.0)) or 0.0)
    thresholds = (gov_ctx or {}).get("risk_thresholds")

    risk_level = _classify_risk(risk_score, thresholds)

    return {
        "decision_overview": {
            "decision_id": rec.get("decision_id") or rec.get("request_id"),
            "request_id": rec.get("request_id"),
            "timestamp": rec.get("ts") or rec.get("created_at"),
            "query": rec.get("query"),
            "decision_status": rec.get("decision_status"),
            "chosen": rec.get("chosen"),
            "source": rec.get("_source_path"),
        },
        "risk_classification": {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "fuji_status": fuji.get("status", rec.get("fuji_status")),
            "violations": fuji.get("violations", []),
            "thresholds_used": thresholds or _DEFAULT_RISK_THRESHOLDS,
        },
        "mitigation_actions": fuji.get("modifications", []),
        "policy_application_evidence": {
            "fuji": fuji,
            "gate": gate,
            "critique_mode": rec.get("critique_mode"),
            "critique_ok": rec.get("critique_ok"),
        },
        "validation_issues": validation_issues,
    }


def _build_integrity_section(decision_id: str) -> Dict[str, Any]:
    signed = verify_trustlog_chain()
    legacy = verify_trust_log()
    replay = _latest_replay_result(decision_id)

    return {
        "signature_verification": {
            "ok": bool(signed.get("ok")),
            "entries_checked": signed.get("entries_checked", 0),
            "issues": signed.get("issues", []),
            "public_key_path": str(PUBLIC_KEY_PATH),
        },
        "replay_verification": replay,
        "hash_chain_integrity": {
            "ok": bool(legacy.get("ok")),
            "checked": legacy.get("checked", 0),
            "broken": bool(legacy.get("broken", False)),
            "broken_reason": legacy.get("broken_reason"),
        },
    }


def _finalize_report(
    report_type: str,
    payload: Dict[str, Any],
    *,
    generated_at: Optional[str] = None,
) -> ReportArtifact:
    ts = generated_at or _utc_now()
    body = {
        "report_type": report_type,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": ts,
        **payload,
    }
    report_hash = sha256_of_canonical_json(body)

    if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
        store_keypair(PRIVATE_KEY_PATH, PUBLIC_KEY_PATH)
    signature = sign_payload_hash(report_hash, PRIVATE_KEY_PATH)

    body["signed_report_hash"] = {
        "algorithm": "SHA-256+Ed25519",
        "report_hash": report_hash,
        "signature": signature,
        "public_key_path": str(PUBLIC_KEY_PATH),
    }

    # Derive report_id from the (possibly injected) timestamp so that file
    # names are deterministic when generated_at is supplied.
    try:
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        ts_dt = datetime.now(timezone.utc)
    report_id = f"{report_type}_{ts_dt.strftime('%Y%m%d_%H%M%S')}"
    json_path = REPORT_DIR / f"{report_id}.json"
    pdf_path = REPORT_DIR / f"{report_id}.pdf"
    persist_report_json(json_path, body)
    persist_report_pdf(pdf_path, body)

    body["artifacts"] = {
        "json_path": str(json_path),
        "pdf_path": str(pdf_path),
    }
    return ReportArtifact(report=body, json_path=json_path, pdf_path=pdf_path)


def _compute_evidence_completeness(
    rec: Dict[str, Any],
    integrity: Dict[str, Any],
    gov_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """Score evidence completeness (0.0–1.0) with per-component breakdown.

    Each component contributes equally.  A missing or failed component
    scores 0; a degraded component scores 0.5.
    """
    components: Dict[str, float] = {}

    # Decision record basics
    gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else None
    fuji = rec.get("fuji") if isinstance(rec.get("fuji"), dict) else None
    components["gate"] = 1.0 if gate is not None else 0.0
    components["fuji"] = 1.0 if fuji is not None else 0.0
    components["timestamp"] = 1.0 if (rec.get("ts") or rec.get("created_at")) else 0.0

    # Replay
    replay = integrity.get("replay_verification", {})
    if replay.get("available") and replay.get("valid", True):
        components["replay"] = 1.0
    elif replay.get("available"):
        components["replay"] = 0.5
    else:
        components["replay"] = 0.0

    # Trustlog
    sig_ok = integrity.get("signature_verification", {}).get("ok", False)
    chain_ok = integrity.get("hash_chain_integrity", {}).get("ok", False)
    components["trustlog_signature"] = 1.0 if sig_ok else 0.0
    components["hash_chain"] = 1.0 if chain_ok else 0.0

    # Governance
    components["governance_policy"] = 1.0 if gov_ctx.get("policy_available") else 0.0

    total = sum(components.values()) / len(components) if components else 0.0
    return {
        "score": round(total, 4),
        "components": components,
    }


def _build_compliance_narrative(
    rec: Dict[str, Any],
    integrity: Dict[str, Any],
    gov_ctx: Dict[str, Any],
    *,
    validation_issues: Optional[List[str]] = None,
) -> str:
    """Build a human-readable narrative explaining the compliance determination."""
    parts: List[str] = []

    decision_id = rec.get("decision_id") or rec.get("request_id") or "unknown"
    status = rec.get("decision_status", "unknown")
    parts.append(f"Decision {decision_id} had status '{status}'.")

    gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
    risk_score = float(gate.get("risk", rec.get("gate_risk", 0.0)) or 0.0)
    thresholds = gov_ctx.get("risk_thresholds", _DEFAULT_RISK_THRESHOLDS)
    risk_level = _classify_risk(risk_score, thresholds)
    parts.append(f"Risk score {risk_score:.2f} classified as '{risk_level}'.")

    if not gov_ctx.get("policy_available"):
        parts.append("Governance policy was unavailable; default thresholds were used.")
    else:
        parts.append(
            f"Risk thresholds from governance policy "
            f"'{gov_ctx.get('policy_version', 'unknown')}' were applied."
        )

    # Fuji violations
    fuji = rec.get("fuji") if isinstance(rec.get("fuji"), dict) else {}
    violations = fuji.get("violations", [])
    if violations:
        parts.append(
            f"Content safety violations detected: {', '.join(str(v) for v in violations)}."
        )

    replay = integrity.get("replay_verification", {})
    if not replay.get("available"):
        parts.append(
            f"Replay artifact was not available (reason: {replay.get('result', 'unknown')})."
        )
    elif replay.get("match"):
        parts.append("Replay verification confirmed deterministic output.")
    else:
        parts.append("Replay verification detected divergence from original decision.")

    sig_ok = integrity.get("signature_verification", {}).get("ok")
    chain_ok = integrity.get("hash_chain_integrity", {}).get("ok")
    if sig_ok and chain_ok:
        parts.append("Trustlog signature and hash chain integrity verified.")
    else:
        issues = []
        if not sig_ok:
            issues.append("signature verification failed")
        if not chain_ok:
            issues.append("hash chain integrity broken")
        parts.append(f"Integrity issues detected: {', '.join(issues)}.")

    # Validation issues
    if validation_issues:
        parts.append(
            f"Validation issues found: {', '.join(validation_issues)}. Manual review required."
        )

    return " ".join(parts)


def generate_eu_ai_act_report(decision_id: str) -> Dict[str, Any]:
    """Generate EU AI Act-ready report for a single decision."""
    rec = _find_decision(decision_id)
    if rec is None:
        return {
            "ok": False,
            "error": "decision_not_found",
            "decision_id": decision_id,
        }

    gov_ctx = _load_governance_context()
    decision_section = _build_decision_section(rec, gov_ctx)
    integrity_section = _build_integrity_section(
        str(rec.get("request_id") or decision_id),
    )
    validation_issues = decision_section.get("validation_issues", [])
    narrative = _build_compliance_narrative(
        rec, integrity_section, gov_ctx, validation_issues=validation_issues,
    )
    evidence = _compute_evidence_completeness(rec, integrity_section, gov_ctx)

    compliance_status = (
        "pass" if rec.get("decision_status") != "rejected" else "review_required"
    )
    if validation_issues:
        compliance_status = "review_required"

    payload = {
        "scope": "eu_ai_act",
        **decision_section,
        **integrity_section,
        "governance_context": {
            "policy_version": gov_ctx.get("policy_version"),
            "policy_available": gov_ctx.get("policy_available"),
            "policy_updated_at": gov_ctx.get("policy_updated_at", ""),
        },
        "evidence_completeness": evidence,
        "summary": {
            "regulation": "EU AI Act",
            "compliance_status": compliance_status,
            "narrative": narrative,
        },
        "input_sources": {
            "decision_log": rec.get("_source_path"),
            "replay_dir": str(REPLAY_REPORT_DIR),
            "governance_policy_version": gov_ctx.get("policy_version"),
        },
    }
    return {"ok": True, **_finalize_report("eu_ai_act", payload).report}


def generate_internal_governance_report(
    date_range: Tuple[str, str],
) -> Dict[str, Any]:
    """Generate internal governance report for a UTC date range."""
    start_raw, end_raw = date_range
    start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
    if start > end:
        raise ValueError(
            f"date_range start ({start_raw}) must not be after end ({end_raw})"
        )

    gov_ctx = _load_governance_context()

    matched: List[Dict[str, Any]] = []
    skipped_records: List[Dict[str, str]] = []
    for rec in _iter_decision_logs():
        ts_raw = str(rec.get("ts") or rec.get("created_at") or "")
        if not ts_raw:
            skipped_records.append({
                "request_id": str(rec.get("request_id", "unknown")),
                "reason": "missing_timestamp",
            })
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            skipped_records.append({
                "request_id": str(rec.get("request_id", "unknown")),
                "reason": "invalid_timestamp",
            })
            continue
        if start <= ts <= end:
            matched.append(rec)

    decisions = [_build_decision_section(rec, gov_ctx) for rec in matched]
    high_risk = sum(
        1
        for item in decisions
        if item["risk_classification"]["risk_level"] in {"high", "critical"}
    )

    payload = {
        "scope": "internal_governance",
        "date_range": {"from": start_raw, "to": end_raw},
        "decision_count": len(matched),
        "decisions": decisions,
        **_build_integrity_section(matched[0].get("request_id", "unknown") if matched else "unknown"),
        "governance_context": {
            "policy_version": gov_ctx.get("policy_version"),
            "policy_available": gov_ctx.get("policy_available"),
            "policy_updated_at": gov_ctx.get("policy_updated_at", ""),
        },
        "summary": {
            "high_risk_decisions": high_risk,
            "risk_ratio": round(high_risk / len(matched), 4) if matched else 0.0,
            "skipped_records": len(skipped_records),
        },
        "input_sources": {
            "log_dir": str(LOG_DIR),
            "replay_dir": str(REPLAY_REPORT_DIR),
            "governance_policy_version": gov_ctx.get("policy_version"),
        },
        "skipped_records": skipped_records,
    }
    return {"ok": True, **_finalize_report("governance", payload).report}


def generate_risk_summary_report() -> Dict[str, Any]:
    """Generate cross-decision risk summary for enterprise audits."""
    all_logs = list(_iter_decision_logs())
    gov_ctx = _load_governance_context()
    thresholds = gov_ctx.get("risk_thresholds")
    buckets = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for rec in all_logs:
        gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
        risk_score = float(gate.get("risk", rec.get("gate_risk", 0.0)) or 0.0)
        buckets[_classify_risk(risk_score, thresholds)] += 1

    payload = {
        "scope": "risk_summary",
        "decision_count": len(all_logs),
        "risk_distribution": buckets,
        **_build_integrity_section("summary"),
        "governance_context": {
            "policy_version": gov_ctx.get("policy_version"),
            "policy_available": gov_ctx.get("policy_available"),
            "policy_updated_at": gov_ctx.get("policy_updated_at", ""),
        },
        "summary": {"top_risk_level": max(buckets, key=buckets.get) if all_logs else "none"},
        "input_sources": {
            "log_dir": str(LOG_DIR),
            "replay_dir": str(REPLAY_REPORT_DIR),
            "governance_policy_version": gov_ctx.get("policy_version"),
        },
    }
    return {"ok": True, **_finalize_report("risk_summary", payload).report}
