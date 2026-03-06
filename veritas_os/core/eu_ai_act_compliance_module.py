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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import functools
import hashlib
import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping


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

ARTICLE_5_PROHIBITED_PATTERNS = (
    "subliminal",
    "social scoring",
    "exploit vulnerability",
    "discriminat",
    "manipulat",
)

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
    """

    enabled: bool = True
    trust_score_threshold: float = 0.8


class EUAIActSafetyGateLayer4(SafetyGate):
    """Layer 4 legal gate extension.

    Art. 5 Prohibited AI Practices:
        Detects obvious prohibited output categories before release.
    Art. 15 Accuracy/Robustness/Cybersecurity:
        Runs deterministic textual checks as a last-mile safeguard.
    """

    layer_name = "layer_4_eu_ai_act"

    def validate_article_5(self, generated_text: str) -> Dict[str, Any]:
        """Validate generated output against Article 5 prohibited practices."""
        lowered = (generated_text or "").lower()
        violations = [
            pattern for pattern in ARTICLE_5_PROHIBITED_PATTERNS if pattern in lowered
        ]
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "layer": self.layer_name,
        }


def classify_annex_iii_risk(prompt: str) -> Dict[str, Any]:
    """Classify prompt risk based on Annex III high-risk domains.

    Art. 9 Risk Management:
        This is the iterative pre-check entry point for risk identification.
    """
    lowered = (prompt or "").lower()
    matched: List[str] = [
        keyword for keyword in ANNEX_III_RISK_KEYWORDS if keyword in lowered
    ]
    if not matched:
        return {"risk_level": "LOW", "risk_score": 0.2, "matched_categories": []}

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
) -> Dict[str, Any]:
    """Apply human-in-the-loop pause logic.

    Art. 14 Human Oversight:
        Force pause when confidence is low or decision context is high-risk.
    """
    should_pause = float(trust_score) < threshold or (risk_level or "").upper() == "HIGH"
    if should_pause:
        response_payload["status"] = "PENDING_HUMAN_REVIEW"
        response_payload["paused_by"] = "Art.14_human_oversight_hook"
    return dict(response_payload)


def _inject_fundamental_rights_role(kwargs: Dict[str, Any]) -> None:
    debate_roles = kwargs.get("debate_roles")
    if isinstance(debate_roles, list):
        debate_roles.append(dict(FUNDAMENTAL_RIGHTS_ROLE))


def eu_compliance_pipeline(
    *,
    config: EUComplianceConfig | None = None,
) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Decorator for `/v1/decide` compliance pipeline.

    Enforced steps when compliance mode is enabled:
    1) Pre-check (Art. 9): Annex III high-risk classification.
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

            output = func(*args, **kwargs)
            if not isinstance(output, dict):
                output = {"result": output}

            safety_gate = EUAIActSafetyGateLayer4()
            gate_log = safety_gate.validate_article_5(str(output.get("output") or ""))
            output["eu_safety_gate"] = gate_log

            trust_score = float(output.get("trust_score", 1.0))
            output["eu_risk_assessment"] = precheck
            output = apply_human_oversight_hook(
                trust_score=trust_score,
                risk_level=str(precheck.get("risk_level") or "LOW"),
                response_payload=output,
                threshold=active_config.trust_score_threshold,
            )
            return output

        return wrapped

    return decorator
