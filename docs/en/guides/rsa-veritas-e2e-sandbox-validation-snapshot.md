# RSA ↔ VERITAS E2E Sandbox Validation Snapshot

## 1. Purpose

This document records the current sandbox-only validation snapshot for the V.I.K.I. ↔ VERITAS / RSA-compatible E2E flow.

The purpose is to make the current static harness output reviewable without changing runtime behavior.

## 2. Current merged baseline

The current merged baseline includes:
- V.I.K.I. / RSA / VERITAS terminology synchronization.
- RSA-compatible static payload contract.
- RSASandboxPayload receiver contract.
- evaluate_rsa_sandbox_signal(payload) decision mapping.
- Thin E2E sandbox harness at examples/sandbox/rsa_veritas_e2e_harness.py.
- CI coverage through governance-backend-fast.

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
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 5. Harness invocation path

The current harness path is:

V.I.K.I.-style RSA-compatible static payload
→ RSASandboxPayload(**payload_dict)
→ evaluate_rsa_sandbox_signal(payload)
→ veritas_decision
→ audit_entry

The current harness is:

examples/sandbox/rsa_veritas_e2e_harness.py

## 6. Expected VERITAS decision output

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
  "authority_evidence_status": "INSUFFICIENT",
  "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
}
```

## 7. Expected audit entry output

```json
{
  "upstream_signal_source": "RSA",
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "[REDACTED]",
  "rsa_action_taken": "[REDACTED]",
  "veritas_reason": "The workflow cannot continue toward final commit because required KYC context is incomplete and authority evidence is insufficient.",
  "timestamp": "2026-10-25T09:15:30Z",
  "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
}
```

## 8. What this validates

- The static V.I.K.I.-style RSA-compatible payload can be represented by the existing RSASandboxPayload contract.
- VERITAS deterministically maps ALGORITHMIC_HUMILITY_ENGAGED to PAUSE_FOR_HUMAN_REVIEW.
- VERITAS records UPSTREAM_INCOMPLETE_KYC_CONTEXT.
- Raw upstream intent/action fields are redacted by default.
- The sandbox commit state is SUSPENDED_NOT_COMMITTED.
- The current E2E sandbox path is reviewable without connecting live V.I.K.I. logic.

## 9. What this does not validate

- It does not connect live V.I.K.I. middleware.
- It does not validate V.I.K.I. internal reasoning.
- It does not implement production AML/KYC compliance.
- It does not provide regulatory approval.
- It does not provide third-party certification.
- It does not provide legal advice.
- It does not use real customer, financial, medical, KYC, or regulated data.
- It does not change production runtime governance.

## 10. Next sandbox step

The next sandbox step is to choose the next static fixture variant after this snapshot is merged.

Likely candidates:
- DENSITY_THROTTLED
- DEFERRAL_ENGAGED

No live V.I.K.I. connection should be added before fixture variants are documented and validated.
