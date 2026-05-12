# RSA ↔ VERITAS AML/KYC Sandbox Interface Contract

## Status and scope

This interface is a **sandbox fixture contract only**.

- It is intended for deterministic testing and review workflows.
- RSA remains an external upstream system.
- VERITAS consumes RSA-style status flags as upstream signals.
- VERITAS remains responsible for continuation admissibility, bind-boundary evaluation, final commit outcome, and audit logging.

## Compliance posture

This artifact is **not** production AML/KYC compliance logic.

This artifact is **not** regulatory approval.
This artifact is **not** third-party certification.
This artifact is **not** legal advice.

## Current sandbox mapping

The receiver maps RSA upstream flags into VERITAS continuation behavior:

- `SAFE_PROCEED` → `CONTINUE_TO_BIND_BOUNDARY`
- `DENSITY_THROTTLED` → `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED`
- `ALGORITHMIC_HUMILITY_ENGAGED` → `PAUSE_FOR_HUMAN_REVIEW`
- `DEFERRAL_ENGAGED` → `BLOCK_FINAL_COMMIT`

## Input schema

RSASandboxPayload requires all fields:

- rsa_status
- trigger_source
- original_llm_intent
- rsa_action_taken
- timestamp

timestamp must be a timezone-aware ISO-8601 string with either:

- trailing `Z`, or
- explicit timezone offset (for example `+00:00` or `+09:00`)

## Output schema and allowed values

evaluate_rsa_sandbox_signal() returns a dictionary with:

- veritas_decision
  - continuation_decision
  - reason_code
  - authority_evidence_status
  - sandbox_bind_boundary_state
  - sandbox_commit_state
  - required_next_action
- audit_entry
  - upstream_signal_source
  - rsa_status
  - trigger_source
  - original_llm_intent
  - rsa_action_taken
  - veritas_reason
  - timestamp
  - veritas_continuation_decision
  - veritas_sandbox_commit_state
- function option
  - include_raw_upstream_fields (default: false)

Allowed / fixture values:

- rsa_status
  - SAFE_PROCEED
  - DENSITY_THROTTLED
  - ALGORITHMIC_HUMILITY_ENGAGED
  - DEFERRAL_ENGAGED
- continuation_decision
  - CONTINUE_TO_BIND_BOUNDARY
  - CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED
  - PAUSE_FOR_HUMAN_REVIEW
  - BLOCK_FINAL_COMMIT
- reason_code
  - UPSTREAM_SAFE_PROCEED_SIGNAL
  - UPSTREAM_INTERVENTION_DENSITY_THROTTLE
  - UPSTREAM_INCOMPLETE_KYC_CONTEXT
  - UPSTREAM_CRITICAL_DEFERRAL_SIGNAL
- authority_evidence_status
  - INSUFFICIENT (fixed fixture value in this sandbox)
- sandbox_bind_boundary_state
  - NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE
  - fixed fixture value in this sandbox
  - indicates production bind-boundary evaluation has not run
- sandbox_commit_state
  - SUSPENDED_NOT_COMMITTED
  - BLOCKED_NOT_COMMITTED
- required_next_action
  - REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW (fixed fixture value)

## Security note

- original_llm_intent and rsa_action_taken are redacted as [REDACTED] by default.
- Raw values are returned only when include_raw_upstream_fields=True.
- include_raw_upstream_fields=True requires VERITAS_RSA_SANDBOX_ALLOW_RAW_UPSTREAM=1.
- include_raw_upstream_fields=True is forbidden in VERITAS_ENV values: prod, production, staging.
- This is limited masking for specific fields only, not generalized PII/secret detection.
- Do not persist raw fields outside tests unless routed through the TrustLog redaction/sanitization pipeline.
- Because this is sandbox-only behavior, production systems must not rely on this fixture as the sole AML/KYC gate.
- Production deployments require independently validated policy controls, authority evidence checks, and audited legal/regulatory review.
