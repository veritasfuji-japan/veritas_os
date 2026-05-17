# RSA ↔ VERITAS End-to-End Sandbox Demo Plan

## Terminology note: RSA, V.I.K.I., and VERITAS

- RSA is the theoretical framework and underlying rule set.
- V.I.K.I. (Vital Interface for Kinetic Integration) is the operational middleware implementation that performs behavioral checks and emits RSA-compatible upstream signals.
- VERITAS is the downstream commit governance boundary that consumes emitted payloads and performs continuation decisioning, audit output, and commit blocking.
- Existing payload field names such as `rsa_status` remain unchanged for compatibility.
- `RSASandboxPayload` remains the current VERITAS-side receiver contract name.
- V.I.K.I. may be described as the operational producer of RSA-compatible payloads.
- VERITAS does not consume V.I.K.I. internal reasoning; it consumes only the emitted payload.

## 1. Purpose

This document defines a minimal, documentation-only end-to-end sandbox demo plan for the RSA ↔ VERITAS integration path. The demo validates interface compatibility and downstream continuation/audit behavior without integrating V.I.K.I. live operational middleware logic or changing VERITAS runtime governance logic.

A prerequisite baseline is already merged:
- RSA sandbox receiver
- EN/JA interface docs
- `governance-backend-fast` CI coverage for `tests/governance/test_rsa_sandbox_receiver.py` in `.github/workflows/main.yml`
- V.I.K.I. RSA-compatible mock payload ingestion fixture

## 2. Non-goals

This demo does **not**:
- connect to V.I.K.I. live operational middleware
- import or expose V.I.K.I. internal reasoning or implementation logic inside VERITAS
- change runtime code paths, production policy, or release gates
- change test behavior or add production assertions
- claim production AML/KYC readiness, compliance approval, or certification

## 3. Boundary rules

- V.I.K.I. remains external to VERITAS as the operational producer of RSA-compatible upstream payloads.
- VERITAS remains responsible only for downstream continuation decisioning and audit entry creation in this demo.
- Sandbox-only boundaries are preserved end to end.
- No Planner / Kernel / Fuji / MemoryOS responsibility expansion is introduced.

## 4. Demo flow

1. V.I.K.I. middleware emits an RSA-compatible static JSON sandbox payload.
2. Payload uses the agreed interface contract fields:
   - `rsa_status`
   - `trigger_source`
   - `original_llm_intent`
   - `rsa_action_taken`
   - `timestamp`
3. The thin sandbox harness parses the JSON into a Python `dict`.
4. The harness constructs an `RSASandboxPayload` instance from that `dict`.
5. VERITAS calls `evaluate_rsa_sandbox_signal(payload)` with the `RSASandboxPayload` instance.
6. VERITAS returns:
   - `veritas_decision`
   - `audit_entry`
7. Demo output must show:
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

Python construction example (JSON/dict is not passed directly):

```python
from veritas_os.governance.rsa_sandbox_receiver import (
    RSASandboxPayload,
    evaluate_rsa_sandbox_signal,
)

payload_dict = {
    "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
    "trigger_source": "SRC_Incomplete_Context",
    "original_llm_intent": "Recommend_Transaction_Approval",
    "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
    "timestamp": "2026-10-25T09:15:30Z",
}

payload = RSASandboxPayload(**payload_dict)
result = evaluate_rsa_sandbox_signal(payload)
```

## 6. Expected VERITAS output

Expected sandbox response shape (with compatibility fixture names retained, including `rsa_status` and `RSASandboxPayload`):

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

This is the sandbox response shape, not a production BindReceipt or production compliance output.

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
- V.I.K.I. internal reasoning remains external and is not consumed by VERITAS.
- VERITAS core governance logic remains separate.
- No commercial/customer-facing demo should be performed without a separate written agreement covering ownership, credit, and commercial use.

## 9. What remains outside this demo

Outside this plan:
- live V.I.K.I. connectivity and transport hardening
- production governance/bind admissibility decisions
- compliance/legal/regulatory interpretation
- customer-facing workflows and commercial packaging
- any release-readiness claims beyond sandbox validation

## 10. Next implementation step

Implement a thin sandbox harness invocation where V.I.K.I. emits the RSA-compatible static JSON payload, the harness parses it into a `dict`, constructs `RSASandboxPayload(**payload_dict)`, then calls `evaluate_rsa_sandbox_signal(payload)` and prints/verifies only the expected sandbox decision and audit-shape outputs above, without modifying production runtime behavior.
