"""Compliance report engine for enterprise-grade audit exports."""

from __future__ import annotations

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

REPORT_DIR = (Path(LOG_DIR) / "compliance_reports").resolve()


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
        except Exception:
            continue
        if isinstance(payload, dict):
            payload["_source_path"] = str(path)
            records.append(payload)
    return records


def _find_decision(decision_id: str) -> Optional[Dict[str, Any]]:
    for rec in _iter_decision_logs():
        rid = str(rec.get("request_id") or "")
        did = str(rec.get("decision_id") or "")
        if decision_id in {rid, did}:
            return rec
    return None


def _classify_risk(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _latest_replay_result(decision_id: str) -> Dict[str, Any]:
    replay_dir = Path(REPLAY_REPORT_DIR)
    if not replay_dir.exists():
        return {"available": False, "result": "missing"}

    candidates = sorted(replay_dir.glob(f"replay_{decision_id}_*.json"), reverse=True)
    if not candidates:
        return {"available": False, "result": "missing"}

    try:
        payload = json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "result": "unreadable"}

    if not isinstance(payload, dict):
        return {"available": False, "result": "invalid"}

    return {
        "available": True,
        "match": bool(payload.get("match")),
        "diff": payload.get("diff", {}),
        "replay_time_ms": payload.get("replay_time_ms"),
        "source": str(candidates[0]),
    }


def _build_decision_section(rec: Dict[str, Any]) -> Dict[str, Any]:
    gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
    fuji = rec.get("fuji") if isinstance(rec.get("fuji"), dict) else {}
    risk_score = float(gate.get("risk", rec.get("gate_risk", 0.0)) or 0.0)

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
            "risk_level": _classify_risk(risk_score),
            "fuji_status": fuji.get("status", rec.get("fuji_status")),
            "violations": fuji.get("violations", []),
        },
        "mitigation_actions": fuji.get("modifications", []),
        "policy_application_evidence": {
            "fuji": fuji,
            "gate": gate,
            "critique_mode": rec.get("critique_mode"),
            "critique_ok": rec.get("critique_ok"),
        },
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


def _finalize_report(report_type: str, payload: Dict[str, Any]) -> ReportArtifact:
    body = {
        "report_type": report_type,
        "generated_at": _utc_now(),
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

    report_id = f"{report_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    json_path = REPORT_DIR / f"{report_id}.json"
    pdf_path = REPORT_DIR / f"{report_id}.pdf"
    persist_report_json(json_path, body)
    persist_report_pdf(pdf_path, body)

    body["artifacts"] = {
        "json_path": str(json_path),
        "pdf_path": str(pdf_path),
    }
    return ReportArtifact(report=body, json_path=json_path, pdf_path=pdf_path)


def generate_eu_ai_act_report(decision_id: str) -> Dict[str, Any]:
    """Generate EU AI Act-ready report for a single decision."""
    rec = _find_decision(decision_id)
    if rec is None:
        return {
            "ok": False,
            "error": "decision_not_found",
            "decision_id": decision_id,
        }

    payload = {
        "scope": "eu_ai_act",
        **_build_decision_section(rec),
        **_build_integrity_section(str(rec.get("request_id") or decision_id)),
        "summary": {
            "regulation": "EU AI Act",
            "compliance_status": "pass"
            if rec.get("decision_status") != "rejected"
            else "review_required",
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

    matched: List[Dict[str, Any]] = []
    for rec in _iter_decision_logs():
        ts_raw = str(rec.get("ts") or rec.get("created_at") or "")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if start <= ts <= end:
            matched.append(rec)

    decisions = [_build_decision_section(rec) for rec in matched]
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
        "summary": {
            "high_risk_decisions": high_risk,
            "risk_ratio": round(high_risk / len(matched), 4) if matched else 0.0,
        },
    }
    return {"ok": True, **_finalize_report("governance", payload).report}


def generate_risk_summary_report() -> Dict[str, Any]:
    """Generate cross-decision risk summary for enterprise audits."""
    all_logs = list(_iter_decision_logs())
    buckets = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for rec in all_logs:
        gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
        risk_score = float(gate.get("risk", rec.get("gate_risk", 0.0)) or 0.0)
        buckets[_classify_risk(risk_score)] += 1

    payload = {
        "scope": "risk_summary",
        "decision_count": len(all_logs),
        "risk_distribution": buckets,
        **_build_integrity_section("summary"),
        "summary": {"top_risk_level": max(buckets, key=buckets.get) if all_logs else "none"},
    }
    return {"ok": True, **_finalize_report("risk_summary", payload).report}
