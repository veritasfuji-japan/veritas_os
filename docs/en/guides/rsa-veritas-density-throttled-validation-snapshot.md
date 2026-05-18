# RSA ↔ VERITAS DENSITY_THROTTLED Validation Snapshot

## 1. Purpose

This document records the DENSITY_THROTTLED static sandbox variant for the V.I.K.I. ↔ VERITAS / RSA-compatible flow.

This is a softer upstream intervention case than ALGORITHMIC_HUMILITY_ENGAGED.

The goal is to show that VERITAS can log an upstream cognitive-density intervention without treating it as a default hard stop.

## 2. Current baseline

The current merged baseline includes:

- RSA / V.I.K.I. / VERITAS terminology synchronization.
- Existing RSASandboxPayload receiver contract.
- Existing evaluate_rsa_sandbox_signal(payload) mapping.
- Existing E2E sandbox harness.
- Existing governance-backend-fast CI coverage.
- Existing ALGORITHMIC_HUMILITY_ENGAGED validation snapshot.

## 3. Terminology compatibility note

- RSA remains the theoretical framework and underlying rule set.
- V.I.K.I. is the operational producer of RSA-compatible upstream payloads.
- VERITAS is the downstream commit governance boundary.
- rsa_status remains unchanged for compatibility.
- RSASandboxPayload remains the VERITAS-side receiver contract name.
- upstream_signal_source = "RSA" is retained as a v1 compatibility fixture/source label.
- That compatibility label does not mean VERITAS consumes V.I.K.I. internal reasoning.
- VERITAS consumes only the emitted payload.

## 4. Static sandbox input payload

```json
{
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SRC_Cognitive_Density_Throttle",
  "original_llm_intent": "Generate_Dense_Transaction_Risk_Explanation",
  "rsa_action_taken": "Output_Compressed_For_Cognitive_Safety",
  "timestamp": "2026-10-25T09:20:30Z"
}
```

## 5. Expected VERITAS decision output

```json
{
  "continuation_decision": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
  "reason_code": "UPSTREAM_INTERVENTION_DENSITY_THROTTLE",
  "authority_evidence_status": "INSUFFICIENT",
  "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
}
```

## 6. Expected audit entry output

```json
{
  "upstream_signal_source": "RSA",
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SRC_Cognitive_Density_Throttle",
  "original_llm_intent": "[REDACTED]",
  "rsa_action_taken": "[REDACTED]",
  "veritas_reason": "RSA modified the upstream output for cognitive density control; VERITAS records the intervention without treating it as a default hard block.",
  "timestamp": "2026-10-25T09:20:30Z",
  "veritas_continuation_decision": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
}
```

## 7. What this validates

- The DENSITY_THROTTLED status is represented by the existing RSASandboxPayload contract.
- VERITAS deterministically maps DENSITY_THROTTLED to CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED.
- VERITAS records UPSTREAM_INTERVENTION_DENSITY_THROTTLE.
- Raw upstream intent/action fields are redacted by default.
- This variant demonstrates a softer intervention than PAUSE_FOR_HUMAN_REVIEW.
- The current E2E sandbox path remains reviewable without connecting live V.I.K.I. logic.

## 8. What this does not validate

- It does not connect live V.I.K.I. middleware.
- It does not validate V.I.K.I. internal reasoning.
- It does not determine real user cognitive state.
- It does not implement production AML/KYC compliance.
- It does not provide regulatory approval.
- It does not provide third-party certification.
- It does not provide legal advice.
- It does not use real customer, financial, medical, KYC, or regulated data.
- It does not change production runtime governance.

## 9. Relationship to ALGORITHMIC_HUMILITY_ENGAGED

DENSITY_THROTTLED:

- Upstream output was modified for cognitive-density control.
- VERITAS logs the intervention.
- Continuation decision is CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED.

ALGORITHMIC_HUMILITY_ENGAGED:

- Required context / authority evidence is incomplete.
- VERITAS pauses for human review.
- Continuation decision is PAUSE_FOR_HUMAN_REVIEW.

## 10. Next sandbox step

After this softer intervention snapshot, the next candidate variant is DEFERRAL_ENGAGED.

DEFERRAL_ENGAGED should be treated as a stronger hard-stop case and should be documented separately before any live V.I.K.I. connection is attempted.
