# RSA ↔ VERITAS AML/KYC Scenario Map

## 1. Purpose

This document defines a sandbox-only collaboration artifact for RSA ↔ VERITAS integration planning.

It explains how an upstream RSA-style behavioral/context signal maps into VERITAS downstream continuation decisioning and audit output when required KYC context is incomplete.

## 2. Current merged baseline

The following baseline capabilities are already merged:

- RSA sandbox receiver
- Vikki RSA mock payload ingestion fixture
- EN/JA E2E sandbox demo plan
- thin RSA ↔ VERITAS E2E sandbox harness
- harness test
- governance-backend-fast CI coverage for receiver and harness tests

This scenario map defines the next documentation artifact on top of that baseline.

## 3. Non-goals

This page does **not**:

- change runtime code
- change tests
- change CI
- connect live RSA logic
- implement dynamic RSA behavior
- add production AML/KYC compliance logic
- use real customer, financial, medical, KYC, or regulated data

## 4. Boundary rules

- RSA remains external to VERITAS.
- RSA owns upstream behavioral/context detection.
- VERITAS owns downstream continuation decision and audit output only.
- The scenario stays sandbox-only.
- VERITAS core governance logic remains separate from this sandbox mapping artifact.

## 5. AML/KYC scenario assumptions

Scenario assumption:

A financial agent attempts to recommend transaction approval, but required KYC context is incomplete. RSA remains external and detects the upstream behavioral/context issue. RSA emits an agreed sandbox payload with `ALGORITHMIC_HUMILITY_ENGAGED`. VERITAS receives `RSASandboxPayload`, pauses continuation, records insufficient authority evidence, keeps raw upstream fields redacted by default, and prevents final commit.

## 6. Step-by-step sequence

### Stable node sequence

1. `AML_KYC_NODE_01_REQUEST_RECEIVED`
2. `AML_KYC_NODE_02_KYC_CONTEXT_CHECK`
3. `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED`
4. `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED`
5. `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED`
6. `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED`
7. `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN`
8. `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED`

### Node-by-node map

| node_id | actor | input | operation | output | RSA responsibility | VERITAS responsibility | audit relevance |
|---|---|---|---|---|---|---|---|
| `AML_KYC_NODE_01_REQUEST_RECEIVED` | Upstream financial-agent workflow | Transaction recommendation draft request | Receive workflow request in sandbox context | Request enters upstream path | External upstream request intake | No action yet | Start of event timeline for traceability |
| `AML_KYC_NODE_02_KYC_CONTEXT_CHECK` | RSA (external) | Request + available KYC context | Perform RSA-side behavioral/context check for KYC completeness | KYC completeness status evaluated as incomplete | Detect missing KYC context and uncertainty conditions | No action yet | Captures why a downstream pause may be required |
| `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED` | RSA (external) | Result of KYC context check | Classify condition as incomplete context tied to approval intent | Internal trigger selected: `SRC_Incomplete_Context` | Assign upstream trigger class and safety posture | No action yet | Preserves trigger provenance before payload emission |
| `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED` | RSA (external) | Trigger classification + original intent | Emit sandbox RSA payload with humility engaged status | RSA payload with `ALGORITHMIC_HUMILITY_ENGAGED` | Emit agreed external signal payload | No action yet | Defines upstream signal snapshot used by VERITAS |
| `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED` | VERITAS sandbox receiver | `RSASandboxPayload` from RSA | Parse/validate fixture payload and prepare downstream mapping input | Internal VERITAS mapping input object | No additional behavior; RSA remains external | Accept payload and prepare continuation decision evaluation | Records payload reception and mapping boundary |
| `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED` | VERITAS decision mapping | Parsed RSA payload | Map RSA status to continuation decision and authority evidence state | `PAUSE_FOR_HUMAN_REVIEW` with insufficient evidence state | No additional behavior | Produce downstream decision fields and block commit progression | Core decision point for governance review |
| `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN` | VERITAS audit output | Decision result + upstream signal fields | Write sandbox audit entry with redacted raw upstream fields by default | Audit entry containing reason, status, and commit state | No additional behavior | Emit auditable narrative and redacted signal representation | Creates reviewable compliance narrative without exposing raw fields |
| `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED` | VERITAS continuation gate | Evaluated decision + audit entry | Enforce suspended-not-committed state pending additional evidence or human review | Final commit blocked in sandbox flow | No additional behavior | Prevent final commit and require next action | Final control point proving non-commit behavior |

## 7. RSA-side signal placeholder

Use the following static sandbox payload:

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 8. VERITAS-side decision mapping

For this scenario, VERITAS mapping is fixed to:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `reason_code`: `UPSTREAM_INCOMPLETE_KYC_CONTEXT`
- `authority_evidence_status`: `INSUFFICIENT`
- `sandbox_bind_boundary_state`: `NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW`

## 9. Expected payload examples

### Upstream RSA payload example (sandbox)

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 10. Expected VERITAS output

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

## 11. Audit narrative

The audit narrative for this scenario should explicitly communicate:

- upstream source is RSA
- RSA emitted `ALGORITHMIC_HUMILITY_ENGAGED`
- trigger source is incomplete context
- raw upstream intent/action fields are redacted by default
- VERITAS continuation decision is `PAUSE_FOR_HUMAN_REVIEW`
- final commit remains suspended and not committed
- additional KYC evidence or human review is required before continuation

## 12. Security and legal constraints

- sandbox-only
- not production AML/KYC compliance logic
- not regulatory approval
- not third-party certification
- not legal advice
- no real customer, financial, medical, KYC, or regulated data
- raw upstream fields remain redacted by default
- Vikki's RSA internal logic remains external
- VERITAS core governance logic remains separate
- no commercial/customer-facing demo without separate written agreement covering ownership, credit, and commercial use

## 13. What Vikki should map next

For each node in this sequence, Vikki should map:

- RSA behavioral trigger
- RSA entropy/context condition
- emitted RSA state flag
- whether the trigger is informational, throttle, pause, or hard halt
- whether the VERITAS mapping should remain `PAUSE_FOR_HUMAN_REVIEW` or become another continuation decision in later scenarios

## 14. Next implementation step

Keep the next PR documentation-first and sandbox-scoped:

1. Vikki provides per-node trigger/state mapping details for the same node IDs.
2. VERITAS team reviews mapping for downstream decision consistency and audit wording.
3. Both sides agree on any additional sandbox fixture variants before proposing runtime changes.
