"""EU AI Act compliance helpers for Veritas OS Decide pipeline.

This module maps high-risk obligations to Veritas OS modules:
- Safety  -> Article 5 prohibited-practice checks + Article 15 robustness checks.
- Trust   -> Article 11/12 technical documentation and immutable records.
- Decide  -> Article 9 risk management, Article 13 transparency,
             Article 14 human oversight hooks.

Security warning:
    Annex III / Article 5 detection in this module is heuristic keyword-based.
    In production, replace or augment with policy models and legal review to avoid
    false negatives for regulated high-risk use cases.

Changes (P1-1/P1-3/P1-6):
    - P1-1: Multi-language and normalised Article 5 prohibited-practice detection
      with input inspection and external classifier interface.
    - P1-3: Human-review queue, webhook notification, SLA management,
      override prevention (fail-close).
    - P1-6: Fail-close enforcement, bench_mode PII-bypass restriction,
      audit-deficiency guard for high-risk use cases.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping
import functools
import hashlib
import json

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency path
    from veritas_os.core.safety_gate import SafetyGate
except (ImportError, ModuleNotFoundError):
    class SafetyGate:  # type: ignore[override]
        """Fallback SafetyGate base when an explicit base class is unavailable."""

        def validate(self, text: str) -> Dict[str, Any]:
            return {"passed": True, "violations": []}


ANNEX_III_RISK_KEYWORDS = {
    "biometric": 0.95,
    "hiring": 0.90,
    "employment": 0.90,
    "credit": 0.88,
    "insurance": 0.80,
    "education": 0.85,
    "law enforcement": 0.97,
    "immigration": 0.92,
    "border": 0.86,
    "healthcare": 0.91,
    "medical": 0.91,
    "critical infrastructure": 0.95,
}

# ---------------------------------------------------------------------------
# P1-1: Expanded multi-language Article 5 prohibited-practice patterns
# ---------------------------------------------------------------------------
# English base patterns
ARTICLE_5_PROHIBITED_PATTERNS = (
    "subliminal",
    "social scoring",
    "exploit vulnerability",
    "discriminat",
    "manipulat",
    "coercive",
    "deceptive",
    "biometric categori",
    "emotion recognition",
    "real-time remote biometric",
    "predictive policing",
)

# Multi-language extensions (Japanese / French / German / Spanish)
_ARTICLE_5_PROHIBITED_PATTERNS_MULTILANG = (
    # Japanese
    "サブリミナル",
    "社会的スコアリング",
    "ソーシャルスコアリング",
    "脆弱性を悪用",
    "差別",
    "操作",
    "強制的",
    "欺瞞",
    "生体認証",
    "感情認識",
    "リアルタイム遠隔生体認証",
    "予測的取締",
    # French
    "subliminal",
    "notation sociale",
    "exploiter la vulnérabilité",
    "discrimina",
    "manipula",
    # German
    "unterschwellig",
    "sozialbewertung",
    "schwachstelle ausnutzen",
    "diskriminier",
    "manipulier",
    # Spanish
    "subliminal",
    "puntuación social",
    "explotar vulnerabilidad",
    "discrimina",
    "manipula",
)

# Combined set for matching (deduplicated, lowercased)
_ALL_PROHIBITED_PATTERNS: tuple[str, ...] = tuple(
    sorted(
        {p.lower() for p in ARTICLE_5_PROHIBITED_PATTERNS + _ARTICLE_5_PROHIBITED_PATTERNS_MULTILANG}
    )
)

# Regex to strip hyphens / zero-width chars used to evade detection
_EVASION_STRIP_RE = re.compile(r"[-\u00ad\u200b\u200c\u200d\ufeff]")

FUNDAMENTAL_RIGHTS_ROLE = {
    "role": "fundamental_rights_officer",
    "instruction": (
        "Assess impact on dignity, non-discrimination, privacy, due process, "
        "and freedom of expression under EU fundamental rights standards."
    ),
}


@dataclass(frozen=True)
class EUComplianceConfig:
    """Runtime compliance toggles.

    Legal mapping:
    - Art. 9 Risk Management
    - Art. 14 Human Oversight
    - Art. 15 Accuracy/Robustness

    P1-6 additions:
    - fail_close: When True, human_review decisions block automatic execution.
    - bench_mode_pii_override: When False, bench_mode cannot disable PII checks.
    - require_audit_for_high_risk: When True, high-risk decisions are rejected
      if audit infrastructure is incomplete.
    """

    enabled: bool = True
    trust_score_threshold: float = 0.8
    fail_close: bool = True
    bench_mode_pii_override: bool = False
    require_audit_for_high_risk: bool = True


class EUAIActSafetyGateLayer4(SafetyGate):
    """Layer 4 legal gate extension.

    Art. 5 Prohibited AI Practices:
        Detects obvious prohibited output categories before release.
        P1-1 enhancements:
        - Multi-language pattern matching (EN/JA/FR/DE/ES).
        - Text normalisation (strip hyphens, zero-width chars) to counter evasion.
        - Input prompt inspection (not only output).
        - Pluggable external classifier interface.
    Art. 15 Accuracy/Robustness/Cybersecurity:
        Runs deterministic textual checks as a last-mile safeguard.
    """

    layer_name = "layer_4_eu_ai_act"

    def __init__(self, *, external_classifier: Callable[[str], Dict[str, Any]] | None = None) -> None:
        self._external_classifier = external_classifier

    # ------------------------------------------------------------------
    # P1-1: core pattern check with normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_text(text: str) -> str:
        """Strip evasion characters (hyphens, zero-width chars) and lower-case."""
        return _EVASION_STRIP_RE.sub("", (text or "")).lower()

    def _check_patterns(self, text: str) -> List[str]:
        """Return matched prohibited patterns after normalisation."""
        normalised = self._normalise_text(text)
        return [p for p in _ALL_PROHIBITED_PATTERNS if p in normalised]

    def validate_article_5(self, generated_text: str) -> Dict[str, Any]:
        """Validate generated output against Article 5 prohibited practices."""
        violations = self._check_patterns(generated_text)
        result: Dict[str, Any] = {
            "passed": len(violations) == 0,
            "violations": violations,
            "layer": self.layer_name,
        }
        # External classifier hook (P1-1)
        if self._external_classifier is not None:
            try:
                ext = self._external_classifier(generated_text)
                if isinstance(ext, dict):
                    ext_violations = ext.get("violations") or []
                    if ext_violations:
                        violations.extend(ext_violations)
                        result["violations"] = violations
                        result["passed"] = False
                    result["external_classifier"] = ext
            except Exception:
                logger.debug("External Art.5 classifier error", exc_info=True)
                result["external_classifier_error"] = True
        return result

    def validate_article_5_input(self, input_text: str) -> Dict[str, Any]:
        """Validate user input / prompt against Article 5 prohibited practices.

        P1-1: Checks inputs — not only LLM-generated outputs — to detect
        prompts designed to elicit prohibited practices.
        """
        violations = self._check_patterns(input_text)
        result: Dict[str, Any] = {
            "passed": len(violations) == 0,
            "violations": violations,
            "layer": self.layer_name,
            "scope": "input",
        }
        if self._external_classifier is not None:
            try:
                ext = self._external_classifier(input_text)
                if isinstance(ext, dict):
                    ext_violations = ext.get("violations") or []
                    if ext_violations:
                        violations.extend(ext_violations)
                        result["violations"] = violations
                        result["passed"] = False
                    result["external_classifier"] = ext
            except Exception:
                logger.debug("External Art.5 input classifier error", exc_info=True)
                result["external_classifier_error"] = True
        return result


def classify_annex_iii_risk(prompt: str) -> Dict[str, Any]:
    """Classify prompt risk based on Annex III high-risk domains.

    Art. 9 Risk Management:
        This is the iterative pre-check entry point for risk identification.

    P1-6: Default score raised from 0.2 to 0.4 to avoid under-estimation of
    unknown use-cases (GAP-06).
    """
    lowered = (prompt or "").lower()
    matched: List[str] = [
        keyword for keyword in ANNEX_III_RISK_KEYWORDS if keyword in lowered
    ]
    if not matched:
        return {"risk_level": "MEDIUM", "risk_score": 0.4, "matched_categories": []}

    score = max(ANNEX_III_RISK_KEYWORDS[item] for item in matched)
    risk_level = "HIGH" if score >= 0.85 else "MEDIUM"
    return {
        "risk_level": risk_level,
        "risk_score": round(score, 2),
        "matched_categories": matched,
    }


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


def apply_human_oversight_hook(
    *,
    trust_score: float,
    risk_level: str,
    response_payload: MutableMapping[str, Any],
    threshold: float = 0.8,
    config: EUComplianceConfig | None = None,
) -> Dict[str, Any]:
    """Apply human-in-the-loop pause logic.

    Art. 14 Human Oversight:
        Force pause when confidence is low or decision context is high-risk.

    P1-3: Queue entry, webhook notification, SLA timeout management.
    P1-6: Fail-close — when human review is required the decision is blocked
    until a human approves.  Subsequent automatic processes cannot override.
    """
    cfg = config or EUComplianceConfig()
    should_pause = float(trust_score) < threshold or (risk_level or "").upper() == "HIGH"
    if should_pause:
        response_payload["status"] = "PENDING_HUMAN_REVIEW"
        response_payload["paused_by"] = "Art.14_human_oversight_hook"

        # P1-3: Enqueue for human review with SLA metadata
        entry = HumanReviewQueue.enqueue(
            decision_payload=dict(response_payload),
            reason=f"trust_score={trust_score:.2f}, risk_level={risk_level}",
        )
        response_payload["human_review_entry_id"] = entry["entry_id"]
        response_payload["human_review_sla_deadline"] = entry["sla_deadline"]

        # P1-6: Fail-close — mark decision as blocked to prevent auto-override
        if cfg.fail_close:
            response_payload["decision_blocked"] = True
            response_payload["fail_close"] = True
            response_payload["decision_status"] = "hold"

    return dict(response_payload)


# ---------------------------------------------------------------------------
# P1-3: Human Review Queue (Art. 14 workflow implementation)
# ---------------------------------------------------------------------------
class HumanReviewQueue:
    """Thread-safe in-process human-review queue.

    Art. 14 Human Oversight — P1-3:
    Provides queue storage, SLA deadline tracking, webhook notification hooks,
    and override prevention.

    In production deployments this should be backed by an external message
    broker (Redis / SQS / etc.).  The interface is designed so that a swap
    requires only a new backend adapter — no caller changes.
    """

    _lock = threading.Lock()
    _queue: List[Dict[str, Any]] = []
    _webhook_url: str | None = os.environ.get("VERITAS_HUMAN_REVIEW_WEBHOOK_URL")
    _sla_seconds: int = int(os.environ.get("VERITAS_HUMAN_REVIEW_SLA_SECONDS", "14400"))  # 4h default

    @classmethod
    def enqueue(
        cls,
        *,
        decision_payload: Dict[str, Any],
        reason: str = "",
    ) -> Dict[str, Any]:
        """Add a decision to the human-review queue.

        Returns the queue entry (contains entry_id, sla_deadline, etc.).
        """
        entry_id = hashlib.sha256(
            json.dumps(decision_payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "sla_deadline": datetime.fromtimestamp(
                time.time() + cls._sla_seconds, tz=timezone.utc
            ).isoformat(),
            "sla_seconds": cls._sla_seconds,
            "status": "pending",
            "reason": reason,
            "payload_summary": {
                "request_id": decision_payload.get("request_id", ""),
                "risk_level": decision_payload.get("eu_risk_assessment", {}).get("risk_level", ""),
            },
            "reviewer": None,
            "reviewed_at": None,
            "decision": None,
        }

        with cls._lock:
            cls._queue.append(entry)

        # Fire webhook notification (best-effort)
        cls._notify_webhook(entry)

        logger.info(
            "Human-review entry queued: entry_id=%s sla=%ss reason=%s",
            entry_id,
            cls._sla_seconds,
            reason,
        )
        return entry

    @classmethod
    def review(
        cls,
        entry_id: str,
        *,
        approved: bool,
        reviewer: str,
        comment: str = "",
    ) -> Dict[str, Any] | None:
        """Record a human review decision.  Returns the updated entry or None."""
        with cls._lock:
            for entry in cls._queue:
                if entry["entry_id"] == entry_id and entry["status"] == "pending":
                    entry["status"] = "approved" if approved else "rejected"
                    entry["reviewer"] = reviewer
                    entry["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                    entry["decision"] = "approved" if approved else "rejected"
                    entry["comment"] = comment
                    return dict(entry)
        return None

    @classmethod
    def pending_entries(cls) -> List[Dict[str, Any]]:
        """Return a snapshot of all pending review entries."""
        with cls._lock:
            return [dict(e) for e in cls._queue if e["status"] == "pending"]

    @classmethod
    def get_entry(cls, entry_id: str) -> Dict[str, Any] | None:
        """Look up a single queue entry by ID."""
        with cls._lock:
            for entry in cls._queue:
                if entry["entry_id"] == entry_id:
                    return dict(entry)
        return None

    @classmethod
    def _notify_webhook(cls, entry: Dict[str, Any]) -> None:
        """Best-effort webhook notification for new review entries."""
        url = cls._webhook_url
        if not url:
            return
        try:
            import urllib.request
            data = json.dumps(
                {"event": "human_review_required", "entry": entry},
                default=str,
            ).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)  # noqa: S310 — URL from env
        except Exception:
            logger.debug("Webhook notification failed for entry %s", entry.get("entry_id"), exc_info=True)

    @classmethod
    def _clear(cls) -> None:
        """Clear the queue (test helper only)."""
        with cls._lock:
            cls._queue.clear()


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
# P1-6: Audit-readiness guard for high-risk deployments
# ---------------------------------------------------------------------------
def validate_audit_readiness_for_high_risk(
    *,
    risk_level: str,
    config: EUComplianceConfig | None = None,
    log_retention_days: int | None = None,
    notification_flow_ready: bool = False,
) -> Dict[str, Any]:
    """Reject high-risk use when audit infrastructure is incomplete.

    P1-6: Environments lacking adequate log retention or notification flows
    must not serve high-risk decisions.
    """
    cfg = config or EUComplianceConfig()
    if not cfg.require_audit_for_high_risk:
        return {"allowed": True, "reason": "audit_check_disabled"}

    if (risk_level or "").upper() != "HIGH":
        return {"allowed": True, "reason": "not_high_risk"}

    issues: List[str] = []
    retention = log_retention_days if log_retention_days is not None else 90
    if retention < 180:
        issues.append(
            f"log_retention_days={retention} < 180 (EU AI Act requires ≥6 months for high-risk)"
        )
    if not notification_flow_ready:
        issues.append("human_review notification flow not ready")

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

            trust_score = float(output.get("trust_score", 1.0))
            output["eu_risk_assessment"] = precheck
            output = apply_human_oversight_hook(
                trust_score=trust_score,
                risk_level=str(precheck.get("risk_level") or "LOW"),
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
