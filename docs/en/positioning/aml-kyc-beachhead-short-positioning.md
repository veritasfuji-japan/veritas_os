# AML/KYC Beachhead Short Positioning (Customer / Operator / Investor)

## Scope and fact boundary

This page summarizes the current, implemented AML/KYC beachhead posture.
It does not claim legal determination automation or unattended production
operations beyond documented governance controls.

Implemented references:
- [1-day PoC quickstart](../guides/poc-pack-financial-quickstart.md)
- [Financial governance templates](../guides/financial-governance-templates.md)
- [External audit readiness](../validation/external-audit-readiness.md)

## Customer-facing short explanation

VERITAS OS provides a governance layer before execution for AML/KYC workflows.
In the beachhead pack, ambiguous or evidence-missing cases are routed to hold,
block, or human review paths instead of silent auto-proceed, with replayable and
audit-oriented decision artifacts.

## Operator-facing short explanation

The AML/KYC beachhead is an executable PoC path: run fixture-based scenarios via
`scripts/run_financial_poc.py`, compare expected semantics against runtime
output, triage mismatch summaries, and move successful runs into evidence-bundle
readiness checks for external review handoff.

## Investor-facing short explanation

The AML/KYC beachhead shows productization discipline: not only model outcomes
but measurable governance behavior. VERITAS OS already provides fail-closed
decision gates, evidence-key based semantics checks, and a path to independently
verifiable audit bundles. Positioning remains bounded to implemented controls and
does not assume universal production certification.
