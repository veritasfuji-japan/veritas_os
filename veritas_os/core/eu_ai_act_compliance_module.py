"""EU AI Act compliance helpers for Veritas OS Decide pipeline.

This module maps high-risk obligations to Veritas OS modules:
- Safety  -> Article 5 prohibited-practice checks + Article 15 robustness checks.
- Trust   -> Article 11/12 technical documentation and immutable records.
- Decide  -> Article 9 risk management, Article 13 transparency,
             Article 14 human oversight hooks.

Security warning:
    Annex III / Article 5 detection in this module is heuristic keyword-based
    with n-gram semantic similarity augmentation.
    In production, replace or augment with policy models and legal review to avoid
    false negatives for regulated high-risk use cases.

Changes (P1-1/P1-3/P1-6):
    - P1-1: Multi-language and normalised Article 5 prohibited-practice detection
      with input inspection and external classifier interface.
    - P1-3: Human-review queue, webhook notification, SLA management,
      override prevention (fail-close).
    - P1-6: Fail-close enforcement, bench_mode PII-bypass restriction,
      audit-deficiency guard for high-risk use cases.

Changes (P2-3):
    - P2-3: Synthetic-data-only validation for bench_mode.  Real PII markers
      in bench/internal_eval data are rejected unless explicitly overridden.

Changes (GAP-01/GAP-02 review improvements):
    - GAP-01: N-gram semantic similarity detection for Art. 5 prohibited
      practices, providing coverage beyond exact keyword substring matching.
    - GAP-02: Legal approval validation (``validate_legal_approval()``) and
      CE marking readiness check (``validate_ce_marking_readiness()``),
      integrated into ``validate_deployment_readiness()``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping
import functools
import hashlib
import json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical imports — Art. 5 detection lives in ``eu_ai_act_prohibited``,
# human oversight in ``eu_ai_act_oversight``, and the shared config dataclass
# in ``eu_ai_act_config``.  Re-exported here for backward compatibility.
# ---------------------------------------------------------------------------
from veritas_os.core.eu_ai_act_config import EUComplianceConfig  # noqa: F401
from veritas_os.core.eu_ai_act_prohibited import (  # noqa: F401
    ANNEX_III_RISK_KEYWORDS,
    ARTICLE_5_PROHIBITED_PATTERNS,
    EUAIActSafetyGateLayer4,
    FUNDAMENTAL_RIGHTS_ROLE,
    _char_ngrams,
    _ngram_similarity,
    _semantic_ngram_check,
    classify_annex_iii_risk,
    normalise_text,
)
from veritas_os.core.eu_ai_act_oversight import (  # noqa: F401
    DEFAULT_HUMAN_REVIEW_SLA_SECONDS,
    HumanReviewQueue,
    SystemHaltController,
    apply_human_oversight_hook,
)


def build_tamper_evident_trustlog_package(
    *,
    system_state: Mapping[str, Any],
    uncertainty_score: float,
    evidence_sources: Iterable[str],
    safety_gate_log: Mapping[str, Any],
    previous_hash: str = "GENESIS",
) -> Dict[str, Any]:
    """Build immutable TrustLog package.

    Art. 11/12 Technical Documentation & Record Keeping:
        Packages inference state, uncertainty, evidence provenance, and gate
        results into canonical JSON with chained SHA-256 digest.
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_state": dict(system_state),
        "uncertainty_score": float(uncertainty_score),
        "evidence_sources": sorted({str(src) for src in evidence_sources}),
        "safety_gate_log": dict(safety_gate_log),
        "sha256_prev": previous_hash,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload



# ---------------------------------------------------------------------------
# P1-6: Bench-mode PII safeguard
# ---------------------------------------------------------------------------
def validate_bench_mode_pii_safety(
    *,
    mode: str,
    config: EUComplianceConfig | None = None,
) -> Dict[str, Any]:
    """Reject or restrict bench_mode when PII bypass is prohibited.

    P1-6: bench_mode must not disable PII protection unless the deployment
    has explicitly opted in (bench_mode_pii_override=True).
    Returns a dict with ``allowed`` and ``reason``.
    """
    cfg = config or EUComplianceConfig()
    if mode in ("bench", "internal_eval") and not cfg.bench_mode_pii_override:
        return {
            "allowed": False,
            "reason": (
                "bench_mode PII bypass is disabled by EU AI Act compliance policy "
                "(P1-6).  Set bench_mode_pii_override=True only with synthetic data."
            ),
        }
    return {"allowed": True, "reason": ""}


# ---------------------------------------------------------------------------
# P2-3: Bench-mode synthetic-data-only validation
# ---------------------------------------------------------------------------
# Heuristic markers that suggest real (non-synthetic) PII is present.
# These are intentionally broad patterns to err on the side of caution.
_REAL_PII_MARKERS: tuple[str, ...] = (
    "@gmail.",
    "@yahoo.",
    "@outlook.",
    "@hotmail.",
    "@icloud.",
    # Social-security / national-ID style patterns
    "ssn",
    "social security",
    "passport number",
    "national id",
    "マイナンバー",
    "住民票",
    # Credit-card-style runs (simplified heuristic)
    "credit card",
    "card number",
)

_REAL_PII_MARKER_RE = re.compile(
    # 4-groups of 4 digits (credit-card pattern) or XXX-XX-XXXX (SSN pattern)
    r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b"
    r"|\b\d{3}-\d{2}-\d{4}\b",
)


def validate_bench_mode_synthetic_data(
    *,
    mode: str,
    data_text: str,
    config: EUComplianceConfig | None = None,
) -> Dict[str, Any]:
    """Validate that bench/internal_eval mode uses only synthetic data.

    P2-3: When running in bench_mode, any text data passed through the
    pipeline is scanned for real-PII markers.  If a real-PII marker is
    detected and ``bench_mode_pii_override`` is **not** set, the request
    is rejected to comply with Art. 15 / GAP-11.

    Returns a dict with ``passed``, ``reason``, and ``detected_markers``.
    """
    cfg = config or EUComplianceConfig()

    if mode not in ("bench", "internal_eval"):
        return {"passed": True, "reason": "not_bench_mode", "detected_markers": []}

    if cfg.bench_mode_pii_override:
        return {
            "passed": True,
            "reason": "bench_mode_pii_override_enabled",
            "detected_markers": [],
        }

    lowered = (data_text or "").lower()
    detected: List[str] = [m for m in _REAL_PII_MARKERS if m in lowered]

    if _REAL_PII_MARKER_RE.search(data_text or ""):
        detected.append("pii_numeric_pattern")

    if detected:
        return {
            "passed": False,
            "reason": (
                "Real PII markers detected in bench_mode data. "
                "Use synthetic data only (P2-3 / Art. 15 / GAP-11). "
                f"Detected: {', '.join(detected)}"
            ),
            "detected_markers": detected,
        }

    return {"passed": True, "reason": "synthetic_data_check_passed", "detected_markers": []}


# ---------------------------------------------------------------------------
# P1-6: Governance config reading helper
# ---------------------------------------------------------------------------
def _read_governance_log_retention() -> int:
    """Read log retention days from ``governance.json``.

    Falls back to 90 if the file is missing or malformed so that existing
    behaviour is preserved when governance.json is not available.
    """
    try:
        governance_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "api", "governance.json",
        )
        with open(governance_path) as fh:
            gov = json.load(fh)
        return int(gov.get("log_retention", {}).get("retention_days", 90))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 90


# ---------------------------------------------------------------------------
# P1-6: Audit-readiness guard for high-risk deployments
# ---------------------------------------------------------------------------
def validate_audit_readiness_for_high_risk(
    *,
    risk_level: str,
    config: EUComplianceConfig | None = None,
    log_retention_days: int | None = None,
    notification_flow_ready: bool | None = None,
    encryption_enabled: bool | None = None,
) -> Dict[str, Any]:
    """Reject high-risk use when audit infrastructure is incomplete.

    P1-6: Environments lacking adequate log retention, notification flows,
    or at-rest encryption must not serve high-risk decisions.

    When *log_retention_days*, *notification_flow_ready*, or
    *encryption_enabled* are ``None`` the function auto-detects the
    current environment state:

    * ``log_retention_days`` — read from ``governance.json``.
    * ``notification_flow_ready`` — ``True`` when
      ``VERITAS_HUMAN_REVIEW_WEBHOOK_URL`` is set.
    * ``encryption_enabled`` — ``True`` when
      ``VERITAS_ENCRYPTION_KEY`` is set.
    """
    cfg = config or EUComplianceConfig()
    if not cfg.require_audit_for_high_risk:
        return {"allowed": True, "reason": "audit_check_disabled"}

    if (risk_level or "").upper() != "HIGH":
        return {"allowed": True, "reason": "not_high_risk"}

    # Auto-detect values from the environment when not explicitly provided.
    if log_retention_days is None:
        log_retention_days = _read_governance_log_retention()

    if notification_flow_ready is None:
        notification_flow_ready = bool(
            os.environ.get("VERITAS_HUMAN_REVIEW_WEBHOOK_URL")
        )

    if encryption_enabled is None:
        encryption_enabled = bool(os.environ.get("VERITAS_ENCRYPTION_KEY"))

    issues: List[str] = []

    if log_retention_days < 180:
        issues.append(
            f"log_retention_days={log_retention_days} < 180 "
            "(EU AI Act requires ≥6 months for high-risk)"
        )
    if not notification_flow_ready:
        issues.append("human_review notification flow not ready")
    if not encryption_enabled:
        issues.append(
            "at-rest encryption not enabled "
            "(set VERITAS_ENCRYPTION_KEY for high-risk deployments)"
        )

    if issues:
        return {
            "allowed": False,
            "reason": "audit_readiness_insufficient: " + "; ".join(issues),
        }
    return {"allowed": True, "reason": "audit_ready"}


def _inject_fundamental_rights_role(kwargs: Dict[str, Any]) -> None:
    debate_roles = kwargs.get("debate_roles")
    if isinstance(debate_roles, list):
        debate_roles.append(dict(FUNDAMENTAL_RIGHTS_ROLE))


def eu_compliance_pipeline(
    *,
    config: EUComplianceConfig | None = None,
) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Decorator for ``/v1/decide`` compliance pipeline.

    Enforced steps when compliance mode is enabled:
    0) System halt check (Art. 14(4)): Refuse all requests if halted.
    1) Pre-check (Art. 9): Annex III high-risk classification.
    1b) Input inspection (Art. 5 / P1-1): Check prompt for prohibited practices.
    1c) Bench-mode guard (P1-6): Block PII bypass unless explicitly allowed.
    1d) Audit-readiness guard (P1-6): Block high-risk if audit infra is incomplete.
    2) In-process (Art. 13): Fundamental-rights deliberation role injection.
    3) Post-check (Art. 5): Safety gate validation for prohibited practices.
    4) Oversight hook (Art. 14): Pause on high-risk or low trust score.
    """
    active_config = config or EUComplianceConfig()

    def decorator(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        @functools.wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            if not active_config.enabled:
                return func(*args, **kwargs)

            # Art. 14(4): System halt check — refuse all requests when halted
            if SystemHaltController.is_halted():
                halt_status = SystemHaltController.status()
                return {
                    "output": "",
                    "status": "HALTED",
                    "decision_status": "rejected",
                    "blocked_by": "Art.14(4)_system_halt",
                    "rejection_reason": (
                        "System is halted by a human operator. "
                        f"Reason: {halt_status.get('reason', 'N/A')}"
                    ),
                    "halt_status": halt_status,
                }

            prompt = str(kwargs.get("prompt") or "")
            precheck = classify_annex_iii_risk(prompt)
            kwargs["eu_risk_assessment"] = precheck
            _inject_fundamental_rights_role(kwargs)

            # P1-1: Input inspection for prohibited practices
            safety_gate = EUAIActSafetyGateLayer4()
            input_gate = safety_gate.validate_article_5_input(prompt)
            if not input_gate["passed"]:
                return {
                    "output": "",
                    "eu_safety_gate_input": input_gate,
                    "eu_risk_assessment": precheck,
                    "status": "BLOCKED",
                    "blocked_by": "Art.5_input_inspection",
                    "decision_status": "rejected",
                    "rejection_reason": (
                        "Input contains prohibited practices (Art. 5): "
                        + ", ".join(input_gate["violations"])
                    ),
                }

            # P1-6: Bench-mode PII safeguard
            mode = str(kwargs.get("mode") or "")
            bench_check = validate_bench_mode_pii_safety(mode=mode, config=active_config)
            if not bench_check["allowed"]:
                kwargs.setdefault("pii_override_blocked", True)

            # P2-3: Bench-mode synthetic-data-only validation
            if mode in ("bench", "internal_eval"):
                synth_check = validate_bench_mode_synthetic_data(
                    mode=mode, data_text=prompt, config=active_config,
                )
                if not synth_check["passed"]:
                    return {
                        "output": "",
                        "eu_risk_assessment": precheck,
                        "status": "BLOCKED",
                        "blocked_by": "P2-3_synthetic_data_only",
                        "decision_status": "rejected",
                        "rejection_reason": synth_check["reason"],
                        "detected_markers": synth_check["detected_markers"],
                    }

            # P1-6: Audit-readiness guard for high-risk
            if precheck.get("risk_level") == "HIGH":
                audit_check = validate_audit_readiness_for_high_risk(
                    risk_level="HIGH",
                    config=active_config,
                )
                if not audit_check["allowed"]:
                    return {
                        "output": "",
                        "eu_risk_assessment": precheck,
                        "status": "BLOCKED",
                        "blocked_by": "Art.9_audit_readiness",
                        "decision_status": "rejected",
                        "rejection_reason": audit_check["reason"],
                    }

            output = func(*args, **kwargs)
            if not isinstance(output, dict):
                output = {"result": output}

            gate_log = safety_gate.validate_article_5(str(output.get("output") or ""))
            output["eu_safety_gate"] = gate_log

            # GAP-04: Attach machine-readable AI content watermark (Art. 50(2))
            decision_id = str(
                output.get("request_id")
                or output.get("decision_id")
                or hashlib.sha256(prompt.encode()).hexdigest()[:16]
            )
            output["ai_content_watermark"] = build_ai_content_watermark(
                decision_id=decision_id,
            )

            # Art. 13/50: Ensure transparency disclosure fields are present
            # in every response so downstream consumers always receive them.
            output.setdefault("ai_disclosure", AI_DISCLOSURE_TEXT)
            output.setdefault("regulation_notice", AI_REGULATION_NOTICE)

            # Art. 13 / GAP-17: Auto-generate third-party notification for
            # high-risk decisions so that affected_parties_notice is populated.
            risk_level_str = str(precheck.get("risk_level") or "LOW")
            if risk_level_str == "HIGH" and output.get("affected_parties_notice") is None:
                tp_notice = ThirdPartyNotificationService.build_notification(
                    decision_id=decision_id,
                    risk_level=risk_level_str,
                    matched_categories=precheck.get("matched_categories", []),
                    decision_summary=str(output.get("output") or "")[:200],
                )
                if tp_notice:
                    output["affected_parties_notice"] = tp_notice

            trust_score = float(output.get("trust_score", 1.0))
            output["eu_risk_assessment"] = precheck
            output = apply_human_oversight_hook(
                trust_score=trust_score,
                risk_level=risk_level_str,
                response_payload=output,
                threshold=active_config.trust_score_threshold,
                config=active_config,
            )
            return output

        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# P1-4: Art. 50 — AI interaction disclosure constants
# ---------------------------------------------------------------------------
AI_DISCLOSURE_TEXT = (
    "This response was generated by an AI system (VERITAS OS)."
)
AI_REGULATION_NOTICE = (
    "Subject to EU AI Act Regulation (EU) 2024/1689."
)


# ---------------------------------------------------------------------------
# GAP-04: Art. 50(2) — Machine-readable AI content watermark
# ---------------------------------------------------------------------------
def _get_watermark_signing_key() -> bytes:
    """Return the HMAC signing key for AI content watermarks.

    Uses the ``VERITAS_WATERMARK_KEY`` environment variable when available.
    Falls back to a deterministic but deployment-unique key derived from the
    ``VERITAS_ENCRYPTION_KEY`` or a hard-coded default (development only).
    """
    key = os.environ.get("VERITAS_WATERMARK_KEY") or os.environ.get("VERITAS_ENCRYPTION_KEY")
    if key:
        return key.encode("utf-8")
    logger.warning(
        "No VERITAS_WATERMARK_KEY or VERITAS_ENCRYPTION_KEY set — "
        "using development-only fallback key for AI content watermark."
    )
    return b"veritas-os-dev-watermark-key"


def build_ai_content_watermark(
    *,
    decision_id: str,
    model: str = "gpt-4.1-mini",
    producer: str = "VERITAS OS",
) -> Dict[str, Any]:
    """Build machine-readable watermark metadata for AI-generated content.

    Art. 50(2) requires AI-generated content to carry machine-readable
    marking so that downstream consumers can programmatically detect it.
    This follows the C2PA (Coalition for Content Provenance and Authenticity)
    manifest structure.

    P6 hardening: Uses HMAC-SHA256 instead of a plain SHA-256 digest so that
    the watermark can be cryptographically verified by parties that hold the
    signing key.  A bare hash is not a signature — it cannot prove
    authenticity because anyone can recompute it.

    Args:
        decision_id: Unique identifier of the decision that produced the content.
        model: Name of the AI model used for generation.
        producer: Name of the producing system.

    Returns:
        Dict containing C2PA-compatible watermark metadata.
    """
    import hmac

    ts = datetime.now(timezone.utc).isoformat()
    payload = f"{producer}:{decision_id}:{ts}".encode()
    key = _get_watermark_signing_key()
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return {
        "version": "1.1",
        "standard": "C2PA-compatible",
        "ai_generated": True,
        "producer": producer,
        "model": model,
        "decision_id": decision_id,
        "timestamp": ts,
        "regulation": "EU AI Act (EU) 2024/1689",
        "content_credentials": {
            "type": "ai_generated_content",
            "assertion": "c2pa.ai_generated",
            "signature_algorithm": "HMAC-SHA256",
            "signature": signature,
        },
    }


# ---------------------------------------------------------------------------
# GAP-16: Art. 15 — Degraded mode for LLM unavailability
# ---------------------------------------------------------------------------
def build_degraded_response(
    *,
    reason: str,
    prompt: str = "",
    risk_assessment: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a safe degraded-mode response when the LLM is unavailable.

    Art. 15 Accuracy/Robustness — GAP-16:
    When the underlying LLM is unreachable or returns an error, the system
    must not silently fail or produce unvalidated output.  Instead, it
    returns a clearly-marked degraded response that:
    - Discloses that the AI could not process the request.
    - Preserves the risk assessment and audit trail.
    - Recommends human review for the original request.

    Args:
        reason: Human-readable description of the failure.
        prompt: The original user prompt (for audit trail).
        risk_assessment: Pre-computed Annex III risk classification, if any.

    Returns:
        A response dict safe for API serialisation.
    """
    return {
        "output": "",
        "decision_status": "abstain",
        "degraded_mode": True,
        "degraded_reason": reason,
        "ai_disclosure": AI_DISCLOSURE_TEXT,
        "regulation_notice": AI_REGULATION_NOTICE,
        "eu_risk_assessment": risk_assessment or classify_annex_iii_risk(prompt),
        "status": "DEGRADED",
        "recommendation": (
            "The AI system is temporarily unavailable. "
            "Please retry later or escalate to a human decision-maker."
        ),
    }


# ---------------------------------------------------------------------------
# P3-1: Art. 12 — Log retention configuration (GAP-13)
# ---------------------------------------------------------------------------
# EU AI Act requires at least 6 months (180 days) for high-risk AI systems.
# Recommended: 1 year (365 days) for high-risk deployments.
DEFAULT_RETENTION_DAYS = 180
HIGH_RISK_RETENTION_DAYS = 365
# Minimum retention for non-high-risk deployments (days)
MIN_STANDARD_RETENTION_DAYS = 90


def get_retention_config(*, risk_level: str = "LOW") -> Dict[str, Any]:
    """Return log retention configuration based on risk level.

    Art. 12 Record Keeping — P3-1:
    EU AI Act requires high-risk AI systems to retain logs for at least
    6 months.  This helper returns the appropriate retention period.

    Args:
        risk_level: The risk classification (LOW, MEDIUM, HIGH).

    Returns:
        Dict with retention_days, minimum_required_days, and compliant flag.
    """
    is_high = (risk_level or "").upper() == "HIGH"
    retention = HIGH_RISK_RETENTION_DAYS if is_high else DEFAULT_RETENTION_DAYS
    minimum = 180 if is_high else MIN_STANDARD_RETENTION_DAYS

    return {
        "retention_days": retention,
        "minimum_required_days": minimum,
        "risk_level": (risk_level or "LOW").upper(),
        "compliant": retention >= minimum,
        "eu_ai_act_article": "Art. 12",
        "note": (
            "High-risk AI systems require ≥6 months (180 days) log retention "
            "per EU AI Act Art. 12. Recommended: 365 days."
            if is_high
            else "Standard retention period applied."
        ),
    }


# ---------------------------------------------------------------------------
# P3-3: Art. 9 — Continuous risk monitoring schedule (GAP-15)
# ---------------------------------------------------------------------------
RISK_MONITORING_SCHEDULE = {
    "daily": [
        "trust_log_integrity_check",
        "anomaly_detection_review",
    ],
    "weekly": [
        "accuracy_drift_analysis",
        "safety_gate_effectiveness_review",
    ],
    "monthly": [
        "risk_register_update",
        "incident_trend_analysis",
        "human_review_sla_compliance",
    ],
    "quarterly": [
        "bias_assessment_review",
        "red_team_exercise",
        "residual_risk_re_evaluation",
        "third_party_model_compliance_check",
    ],
    "annually": [
        "full_compliance_audit",
        "risk_management_system_review",
        "regulatory_update_assessment",
    ],
}


def assess_continuous_risk_monitoring(
    *,
    completed_activities: Dict[str, list[str]] | None = None,
) -> Dict[str, Any]:
    """Assess the status of continuous risk monitoring activities.

    Art. 9 Risk Management — P3-3:
    EU AI Act requires a continuous, iterative risk management system
    throughout the AI system lifecycle.  This function evaluates which
    scheduled monitoring activities have been completed.

    Args:
        completed_activities: Dict mapping frequency to list of completed
            activity names (e.g. {"daily": ["trust_log_integrity_check"]}).

    Returns:
        Dict with schedule, completion status per frequency, and overall score.
    """
    completed = completed_activities or {}
    results: Dict[str, Any] = {
        "schedule": dict(RISK_MONITORING_SCHEDULE),
        "completion": {},
        "overall_score": 0.0,
        "eu_ai_act_article": "Art. 9",
    }

    total = 0
    done = 0
    for freq, activities in RISK_MONITORING_SCHEDULE.items():
        freq_completed = completed.get(freq, [])
        freq_results = {}
        for act in activities:
            is_done = act in freq_completed
            freq_results[act] = is_done
            total += 1
            if is_done:
                done += 1
        results["completion"][freq] = freq_results

    results["overall_score"] = round(done / total, 2) if total > 0 else 0.0
    results["total_activities"] = total
    results["completed_activities"] = done
    results["compliant"] = results["overall_score"] >= 0.7
    return results


# ---------------------------------------------------------------------------
# P3-4: Art. 13 — Third-party notification for high-risk decisions (GAP-17)
# ---------------------------------------------------------------------------
class ThirdPartyNotificationService:
    """Notification service for individuals affected by high-risk AI decisions.

    Art. 13 Transparency — P3-4:
    When VERITAS OS makes or assists with high-risk decisions (employment,
    credit, insurance, etc.), affected third parties must be notified that
    an AI system was involved in the decision-making process.

    In production, integrate with email/SMS/postal notification providers.
    """

    _lock = threading.Lock()
    _notifications: List[Dict[str, Any]] = []
    _webhook_url: str | None = os.environ.get(
        "VERITAS_THIRD_PARTY_NOTIFICATION_WEBHOOK_URL"
    )

    @classmethod
    def build_notification(
        cls,
        *,
        decision_id: str,
        risk_level: str,
        matched_categories: list[str],
        decision_summary: str = "",
    ) -> Dict[str, Any]:
        """Build a third-party notification record for a high-risk decision.

        Args:
            decision_id: Unique ID of the decision.
            risk_level: Risk classification (HIGH, MEDIUM, LOW).
            matched_categories: Annex III categories matched.
            decision_summary: Brief summary of the decision.

        Returns:
            Notification record dict, or empty dict if not high-risk.
        """
        if (risk_level or "").upper() != "HIGH":
            return {}

        notification: Dict[str, Any] = {
            "notification_id": hashlib.sha256(
                f"{decision_id}:{time.time()}".encode()
            ).hexdigest()[:16],
            "decision_id": decision_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "risk_level": "HIGH",
            "matched_categories": list(matched_categories),
            "decision_summary": decision_summary,
            "ai_disclosure": AI_DISCLOSURE_TEXT,
            "regulation_notice": AI_REGULATION_NOTICE,
            "affected_party_rights": {
                "right_to_explanation": True,
                "right_to_contest": True,
                "right_to_human_review": True,
                "contest_contact": os.environ.get(
                    "VERITAS_CONTEST_CONTACT",
                    "compliance@example.com",
                ),
            },
            "status": "pending_delivery",
        }

        with cls._lock:
            cls._notifications.append(notification)

        # Fire webhook if configured
        cls._notify_webhook(notification)
        return notification

    @classmethod
    def get_notifications(cls, *, decision_id: str | None = None) -> List[Dict[str, Any]]:
        """Retrieve notification records, optionally filtered by decision_id."""
        with cls._lock:
            if decision_id is None:
                return [dict(n) for n in cls._notifications]
            return [
                dict(n) for n in cls._notifications
                if n.get("decision_id") == decision_id
            ]

    @classmethod
    def _notify_webhook(cls, notification: Dict[str, Any]) -> None:
        """Best-effort webhook notification for third-party alerts."""
        from veritas_os.core.eu_ai_act_oversight import _validate_webhook_url

        url = _validate_webhook_url(cls._webhook_url or "")
        if not url:
            return
        try:
            import urllib.request

            data = json.dumps(
                {"event": "third_party_notification", "notification": notification},
                default=str,
            ).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)  # nosec B310
        except Exception:
            logger.warning(
                "Third-party webhook notification failed for %s",
                notification.get("notification_id"),
                exc_info=True,
            )

    @classmethod
    def clear_for_testing(cls) -> None:
        """Clear notifications (test helper only)."""
        with cls._lock:
            cls._notifications.clear()


# ---------------------------------------------------------------------------
# GAP-05: Art. 10 — Data quality validation for dataset writes
# ---------------------------------------------------------------------------
def validate_data_quality(
    *,
    text: str,
    kind: str = "",
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate data quality before ingestion into datasets or memory.

    Art. 10 Data Governance — GAP-05:
    EU AI Act requires that training, validation, and test datasets meet
    quality criteria including relevance, representativeness, and
    freedom from errors.

    This function performs basic quality checks on incoming data records.
    It does *not* replace statistical analysis but catches common issues
    at the point of ingestion.

    Args:
        text: The text content to validate.
        kind: Category / type of the data record.
        meta: Optional metadata dict for the record.

    Returns:
        Dict with ``passed``, ``issues`` (list of issue descriptions),
        and ``quality_score`` (0.0–1.0).
    """
    issues: List[str] = []

    # 1. Non-empty content
    stripped = (text or "").strip()
    if not stripped:
        issues.append("empty_content: text is empty or whitespace-only")

    # 2. Minimum meaningful length (configurable via kind)
    min_len = 10
    if stripped and len(stripped) < min_len:
        issues.append(
            f"too_short: text length {len(stripped)} < minimum {min_len}"
        )

    # 3. Excessive repetition (data quality signal)
    if stripped and len(stripped) >= 20:
        words = stripped.split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.2:
                issues.append(
                    f"low_diversity: unique word ratio {unique_ratio:.2f} < 0.20"
                )

    # 4. Valid kind/category
    valid_kinds = (
        "semantic", "episodic", "procedural", "factual", "training",
        "validation", "test", "feedback",
    )
    if kind and kind not in valid_kinds:
        issues.append(f"unknown_kind: '{kind}' not in {valid_kinds}")

    # 5. Meta integrity (if provided)
    if meta is not None and not isinstance(meta, dict):
        issues.append("invalid_meta: meta must be a dict or None")

    # 6. Encoding check — ensure no null bytes
    if "\x00" in (text or ""):
        issues.append("null_bytes: text contains null byte characters")

    quality_score = max(0.0, 1.0 - 0.25 * len(issues))
    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "quality_score": round(quality_score, 2),
        "eu_ai_act_article": "Art. 10",
    }


# ---------------------------------------------------------------------------
# Art. 11 / Art. 15 — Change management validation
# ---------------------------------------------------------------------------
# Required change-log fields per entry.
_REQUIRED_CHANGE_FIELDS: tuple[str, ...] = (
    "date",
    "author",
    "description",
    "component",
)


def validate_change_management(
    *,
    change_log: List[Dict[str, Any]] | None = None,
    repo_root: str | None = None,
) -> Dict[str, Any]:
    """Validate that change management records exist and are well-formed.

    Art. 11 Technical Documentation / Art. 15 Accuracy-Robustness:
    EU AI Act requires that high-risk AI systems maintain documented
    change management procedures.  Each significant change must be
    recorded with date, author, description, and affected component.

    When *change_log* is ``None`` the function looks for
    ``docs/eu_ai_act/change_log.json`` in the repository root.

    Args:
        change_log: Explicit list of change-log entries for validation.
        repo_root: Repository root directory (auto-detected when ``None``).

    Returns:
        Dict with ``valid`` (bool), ``issues`` (list of problems),
        ``entries_count``, and ``eu_ai_act_article``.
    """
    import pathlib

    issues: List[str] = []

    # Load change log from file if not provided explicitly
    if change_log is None:
        if repo_root is None:
            repo_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)
        log_path = os.path.join(repo_root, "docs", "eu_ai_act", "change_log.json")
        if not os.path.isfile(log_path):
            return {
                "valid": False,
                "issues": [
                    "change_log_missing: docs/eu_ai_act/change_log.json not found"
                ],
                "entries_count": 0,
                "eu_ai_act_article": "Art. 11 / Art. 15",
            }
        try:
            with open(log_path) as fh:
                change_log = json.load(fh)
            if not isinstance(change_log, list):
                return {
                    "valid": False,
                    "issues": ["change_log_format: expected a JSON array"],
                    "entries_count": 0,
                    "eu_ai_act_article": "Art. 11 / Art. 15",
                }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "valid": False,
                "issues": [f"change_log_read_error: {exc}"],
                "entries_count": 0,
                "eu_ai_act_article": "Art. 11 / Art. 15",
            }

    if not change_log:
        issues.append("change_log_empty: no change entries recorded")

    # Validate individual entries
    for idx, entry in enumerate(change_log or []):
        if not isinstance(entry, dict):
            issues.append(f"entry_{idx}: not a dict")
            continue
        for field in _REQUIRED_CHANGE_FIELDS:
            if not entry.get(field):
                issues.append(f"entry_{idx}: missing required field '{field}'")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "entries_count": len(change_log or []),
        "eu_ai_act_article": "Art. 11 / Art. 15",
    }


# ---------------------------------------------------------------------------
# GAP-02: Legal approval validation (Art. 6)
# ---------------------------------------------------------------------------
# Required fields in a legal approval record.
_REQUIRED_LEGAL_APPROVAL_FIELDS: tuple[str, ...] = (
    "approved_by",
    "approval_date",
    "risk_classification",
    "scope",
)

_LEGAL_APPROVAL_PATH = os.path.join("docs", "eu_ai_act", "legal_approval.json")


def validate_legal_approval(
    *,
    approval_record: Dict[str, Any] | None = None,
    repo_root: str | None = None,
) -> Dict[str, Any]:
    """Validate that a legal approval record exists and is well-formed.

    Art. 6 / Annex III — Risk classification & CE marking:
    EU AI Act requires that high-risk AI systems have their risk
    classification formally approved by legal counsel before deployment.

    When *approval_record* is ``None`` the function looks for
    ``docs/eu_ai_act/legal_approval.json`` in the repository root.

    Args:
        approval_record: Explicit approval record dict for validation.
        repo_root: Repository root directory (auto-detected when ``None``).

    Returns:
        Dict with ``valid`` (bool), ``issues`` (list of problems),
        and ``eu_ai_act_article``.
    """
    import pathlib

    issues: List[str] = []

    if approval_record is None:
        if repo_root is None:
            repo_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)
        approval_path = os.path.join(repo_root, _LEGAL_APPROVAL_PATH)
        if not os.path.isfile(approval_path):
            return {
                "valid": False,
                "issues": [
                    "legal_approval_missing: docs/eu_ai_act/legal_approval.json not found"
                ],
                "eu_ai_act_article": "Art. 6 / Annex III",
            }
        try:
            with open(approval_path) as fh:
                approval_record = json.load(fh)
            if not isinstance(approval_record, dict):
                return {
                    "valid": False,
                    "issues": ["legal_approval_format: expected a JSON object"],
                    "eu_ai_act_article": "Art. 6 / Annex III",
                }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "valid": False,
                "issues": [f"legal_approval_read_error: {exc}"],
                "eu_ai_act_article": "Art. 6 / Annex III",
            }

    # Validate required fields
    for field in _REQUIRED_LEGAL_APPROVAL_FIELDS:
        if not approval_record.get(field):
            issues.append(f"legal_approval: missing required field '{field}'")

    # Validate status is explicitly "approved"
    status = str(approval_record.get("status", "")).lower()
    if status != "approved":
        issues.append(
            f"legal_approval: status is '{status}', expected 'approved'"
        )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "eu_ai_act_article": "Art. 6 / Annex III",
    }


# ---------------------------------------------------------------------------
# GAP-02: CE marking readiness check (Art. 6)
# ---------------------------------------------------------------------------
_CE_MARKING_PREREQUISITES: tuple[str, ...] = (
    "risk_classification_approved",
    "technical_documentation_complete",
    "conformity_assessment_done",
    "quality_management_system",
    "post_market_monitoring_plan",
)


def validate_ce_marking_readiness(
    *,
    checklist: Dict[str, bool] | None = None,
    repo_root: str | None = None,
) -> Dict[str, Any]:
    """Check whether CE marking prerequisites are satisfied.

    Art. 6 — High-risk AI systems:
    When an AI system is classified as high-risk under Annex III,
    the provider must complete a conformity assessment and apply
    CE marking before placing the system on the market.

    Args:
        checklist: Explicit dict mapping prerequisite names to completion
            booleans.  When ``None`` the function checks the
            ``ce_marking`` section of ``legal_approval.json``.
        repo_root: Repository root directory (auto-detected when ``None``).

    Returns:
        Dict with ``ready`` (bool), ``missing`` (list of incomplete
        prerequisites), ``completed`` (list), and ``eu_ai_act_article``.
    """
    import pathlib

    if checklist is None:
        if repo_root is None:
            repo_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)
        approval_path = os.path.join(repo_root, _LEGAL_APPROVAL_PATH)
        if os.path.isfile(approval_path):
            try:
                with open(approval_path) as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    checklist = data.get("ce_marking", {})
            except (OSError, json.JSONDecodeError):
                logger.debug("Failed to read CE marking data", exc_info=True)
        if checklist is None:
            checklist = {}

    completed: list[str] = []
    missing: list[str] = []
    for prereq in _CE_MARKING_PREREQUISITES:
        if checklist.get(prereq):
            completed.append(prereq)
        else:
            missing.append(prereq)

    return {
        "ready": len(missing) == 0,
        "completed": completed,
        "missing": missing,
        "eu_ai_act_article": "Art. 6 / Art. 43 (Conformity Assessment)",
    }


# ---------------------------------------------------------------------------
# P1-5: Deployment readiness check — model card / bias / DPA freshness
# ---------------------------------------------------------------------------
# Maximum age (in days) before a compliance artefact is considered stale.
_MODEL_CARD_MAX_AGE_DAYS = 90
_BIAS_ASSESSMENT_MAX_AGE_DAYS = 90
_DPA_CHECKLIST_MAX_AGE_DAYS = 180

# Expected artefact paths (relative to repository root).
_DEPLOYMENT_READINESS_ARTEFACTS: tuple[tuple[str, str, int], ...] = (
    (
        "model_card",
        "docs/eu_ai_act/model_card_gpt41_mini.md",
        _MODEL_CARD_MAX_AGE_DAYS,
    ),
    (
        "bias_assessment",
        "docs/eu_ai_act/bias_assessment_report.md",
        _BIAS_ASSESSMENT_MAX_AGE_DAYS,
    ),
    (
        "dpa_checklist",
        "docs/eu_ai_act/third_party_model_dpa_checklist.md",
        _DPA_CHECKLIST_MAX_AGE_DAYS,
    ),
)


def validate_deployment_readiness(
    *,
    repo_root: str | None = None,
) -> Dict[str, Any]:
    """Check whether compliance artefacts are up-to-date for deployment.

    P1-5 remaining gate: Before deploying in a high-risk context, the
    following artefacts must exist and have been updated within their
    maximum allowed staleness window:
    - Model card (90 days)
    - Bias assessment report (90 days)
    - DPA checklist (180 days)

    P1-6 environment checks (added):
    - At-rest encryption enabled
    - Log retention ≥ 180 days
    - Human-review notification webhook configured

    GAP-02 checks (added):
    - Legal approval record validation (Art. 6)
    - CE marking readiness check (Art. 6 / Art. 43)

    Args:
        repo_root: Absolute path to the repository root.  When ``None``
            the function walks up from this file to locate the repo root.

    Returns:
        Dict with ``ready`` (bool), ``checks`` (per-artefact status),
        ``environment`` (infrastructure readiness), ``legal_approval``,
        ``ce_marking``, ``issues`` (list of human-readable issues),
        and ``eu_ai_act_article``.
    """
    import pathlib

    if repo_root is None:
        # Walk up from this file: core/ -> veritas_os/ -> repo root
        repo_root = str(pathlib.Path(__file__).resolve().parent.parent.parent)

    now = datetime.now(timezone.utc)
    checks: Dict[str, Any] = {}
    issues: List[str] = []

    for name, rel_path, max_age_days in _DEPLOYMENT_READINESS_ARTEFACTS:
        full_path = os.path.join(repo_root, rel_path)
        if not os.path.isfile(full_path):
            checks[name] = {"exists": False, "path": rel_path}
            issues.append(f"{name}: file not found ({rel_path})")
            continue

        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            checks[name] = {"exists": True, "readable": False, "path": rel_path}
            issues.append(f"{name}: unable to read modification time ({rel_path})")
            continue

        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
        age_days = (now - last_modified).days
        stale = age_days > max_age_days

        checks[name] = {
            "exists": True,
            "path": rel_path,
            "last_modified": last_modified.isoformat(),
            "age_days": age_days,
            "max_age_days": max_age_days,
            "stale": stale,
        }
        if stale:
            issues.append(
                f"{name}: last updated {age_days} days ago (max {max_age_days})"
            )

    # P1-6: Environment infrastructure checks
    env_encryption = bool(os.environ.get("VERITAS_ENCRYPTION_KEY"))
    env_webhook = bool(os.environ.get("VERITAS_HUMAN_REVIEW_WEBHOOK_URL"))
    env_retention = _read_governance_log_retention()

    environment: Dict[str, Any] = {
        "encryption_enabled": env_encryption,
        "notification_webhook_configured": env_webhook,
        "log_retention_days": env_retention,
        "log_retention_compliant": env_retention >= 180,
    }

    if not env_encryption:
        issues.append(
            "encryption: at-rest encryption not enabled "
            "(set VERITAS_ENCRYPTION_KEY for high-risk deployments)"
        )
    if not env_webhook:
        issues.append(
            "notification: human-review webhook not configured "
            "(set VERITAS_HUMAN_REVIEW_WEBHOOK_URL)"
        )
    if env_retention < 180:
        issues.append(
            f"log_retention: {env_retention} days < 180 "
            "(EU AI Act requires ≥6 months for high-risk)"
        )

    # Art. 11 / Art. 15: Change management process validation
    cm = validate_change_management(repo_root=repo_root)
    change_management: Dict[str, Any] = {
        "valid": cm["valid"],
        "entries_count": cm["entries_count"],
    }
    if not cm["valid"]:
        cm_issues = cm["issues"]
        summary = "; ".join(cm_issues[:3])
        if len(cm_issues) > 3:
            summary += f" (+{len(cm_issues) - 3} more)"
        issues.append("change_management: " + summary)

    # GAP-02: Legal approval validation (Art. 6)
    la = validate_legal_approval(repo_root=repo_root)
    legal_approval: Dict[str, Any] = {"valid": la["valid"]}
    if not la["valid"]:
        la_issues = la["issues"]
        summary = "; ".join(la_issues[:3])
        if len(la_issues) > 3:
            summary += f" (+{len(la_issues) - 3} more)"
        issues.append("legal_approval: " + summary)

    # GAP-02: CE marking readiness (Art. 6 / Art. 43)
    ce = validate_ce_marking_readiness(repo_root=repo_root)
    ce_marking: Dict[str, Any] = {
        "ready": ce["ready"],
        "missing": ce["missing"],
    }
    if not ce["ready"]:
        issues.append(
            "ce_marking: missing prerequisites: " + ", ".join(ce["missing"][:3])
            + (f" (+{len(ce['missing']) - 3} more)" if len(ce["missing"]) > 3 else "")
        )

    return {
        "ready": len(issues) == 0,
        "checks": checks,
        "environment": environment,
        "change_management": change_management,
        "legal_approval": legal_approval,
        "ce_marking": ce_marking,
        "issues": issues,
        "eu_ai_act_article": "Art. 6 / Art. 10 / Art. 11 / Art. 12 / Art. 15 (P1-5 / P1-6 / GAP-02)",
    }
