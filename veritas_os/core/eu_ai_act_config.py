"""EU AI Act compliance configuration.

Extracted to break circular imports between ``eu_ai_act_compliance_module``,
``eu_ai_act_prohibited``, and ``eu_ai_act_oversight``.
"""

from __future__ import annotations

from dataclasses import dataclass


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
