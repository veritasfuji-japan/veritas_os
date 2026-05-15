# RSA ↔ VERITAS End-to-End Sandbox Demo Plan

## 1. Purpose

This document defines a minimal, documentation-only end-to-end sandbox demo plan for the RSA ↔ VERITAS integration path. The demo validates interface compatibility and downstream continuation/audit behavior without integrating Vikki’s real RSA wrapper or changing VERITAS runtime governance logic.

A prerequisite baseline is already merged:
- RSA sandbox receiver
- EN/JA interface docs
- Tier 1 CI coverage
- Vikki RSA mock payload ingestion fixture

## 2. Non-goals

This demo does **not**:
- connect to Vikki’s real RSA wrapper
- import or expose Vikki’s internal RSA logic inside VERITAS
- change runtime code paths, production policy, or release gates
- change test behavior or add production assertions
- claim production AML/KYC readiness, compliance approval, or certification

## 3. Boundary rules

- RSA remains an external upstream signal source.
- VERITAS remains responsible only for downstream continuation decisioning and audit entry creation in this demo.
- Sandbox-only boundaries are preserved end to end.
- No Planner / Kernel / Fuji / MemoryOS responsibility expansion is introduced.

## 4. Demo flow

1. RSA mock wrapper emits a static JSON payload.
2. Payload uses the agreed interface contract fields:
   - `rsa_status`
   - `trigger_source`
   - `original_llm_intent`
   - `rsa_action_taken`
   - `timestamp`
3. VERITAS consumes this payload via `evaluate_rsa_sandbox_signal()`.
4. VERITAS returns:
   - `veritas_decision`
   - `audit_entry`
5. Demo output must show:
   - `continuation_decision`
   - `reason_code`
   - `sandbox_commit_state`
   - redacted upstream raw fields
   - timestamp preservation
   - audit narrative

## 5. Input payload

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 6. Expected VERITAS output

Expected sandbox response shape:

```json
{
  "veritas_decision": {
    "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
    "authority_evidence_status": "INSUFFICIENT",
    "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
    "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
    "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
  },
  "audit_entry": {
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
}
```

This is the expected sandbox response shape, not a production BindReceipt or production compliance output.

## 7. Audit behavior

The audit entry should:
- preserve the upstream `timestamp` exactly as received
- record that continuation was paused pending additional authority evidence
- include a concise narrative linking upstream incomplete KYC context to downstream suspension
- retain redaction defaults for raw upstream intent/action fields

## 8. Security constraints

- This is sandbox-only.
- This is not production AML/KYC compliance logic.
- This is not regulatory approval.
- This is not third-party certification.
- This is not legal advice.
- Raw upstream fields must remain redacted by default.
- No real customer, financial, medical, KYC, or regulated data should be used.
- Vikki’s RSA internal logic remains external.
- VERITAS core governance logic remains separate.
- No commercial/customer-facing demo should be performed without a separate written agreement covering ownership, credit, and commercial use.

## 9. What remains outside this demo

Outside this plan:
- real RSA wrapper connectivity and transport hardening
- production governance/bind admissibility decisions
- compliance/legal/regulatory interpretation
- customer-facing workflows and commercial packaging
- any release-readiness claims beyond sandbox validation

## 10. Next implementation step

Implement a thin sandbox harness invocation that feeds the static payload into `evaluate_rsa_sandbox_signal()` and prints/verifies only the expected sandbox decision and audit-shape outputs above, without modifying production runtime behavior.
