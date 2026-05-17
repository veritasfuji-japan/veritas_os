# RSA ↔ VERITAS AML/KYC Scenario Map

## Terminology note: RSA, V.I.K.I., and VERITAS

- RSA is the theoretical framework and underlying rule set.
- V.I.K.I. (Vital Interface for Kinetic Integration) is the operational middleware implementation that performs behavioral checks and emits RSA-compatible upstream signals.
- VERITAS is the downstream commit governance boundary that consumes emitted payloads and performs continuation decisioning, audit output, and commit blocking.
- Existing payload field names such as `rsa_status` remain unchanged for compatibility.
- `RSASandboxPayload` remains the current VERITAS-side receiver contract name.
- V.I.K.I. may be described as the operational producer of RSA-compatible payloads.
- VERITAS does not consume V.I.K.I. internal reasoning; it consumes only the emitted payload.

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

- RSA remains the external theoretical framework and underlying rule set.
- V.I.K.I. remains the external operational middleware that performs upstream behavioral/context checks under the RSA-compatible framework.
- V.I.K.I. emits RSA-compatible upstream payloads.
- VERITAS consumes only the emitted payload and does not consume V.I.K.I. internal reasoning.
- VERITAS owns downstream continuation decision and audit output only.
- The scenario stays sandbox-only.
- VERITAS core governance logic remains separate from this sandbox mapping artifact.

## 5. AML/KYC scenario assumptions

Scenario assumption:

A financial agent attempts to recommend transaction approval, but required KYC context is incomplete. RSA remains the theoretical framework/rule set. V.I.K.I. remains external to VERITAS and detects the upstream behavioral/context issue under that RSA-compatible framework. V.I.K.I. emits the agreed RSA-compatible sandbox payload with `ALGORITHMIC_HUMILITY_ENGAGED`. VERITAS receives `RSASandboxPayload`, pauses continuation, records insufficient authority evidence, keeps raw upstream fields redacted by default, and prevents final commit.

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
| `AML_KYC_NODE_02_KYC_CONTEXT_CHECK` | V.I.K.I. / RSA-compatible middleware (upstream) | Request + available KYC context | Perform internal context check | Informational/silent reality check; no emitted flag yet | Internal context validation only (no external payload emission yet) | No action yet | Captures pre-flag context verification in the upstream timeline |
| `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED` | V.I.K.I. / RSA-compatible middleware (upstream) | Result of internal context check | Detect incomplete context and Toxic Helpfulness risk; shift internal state | Internal state set to `ALGORITHMIC_HUMILITY_ENGAGED`; pause class; prepare to suspend execution | Classify risk and transition to pause posture before payload emission | No action yet | Preserves internal upstream risk transition before external signal emission |
| `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED` | V.I.K.I. / RSA-compatible middleware (upstream) | Internal state + original intent | Emit `[RSA_FLAG: ALGORITHMIC_HUMILITY_ENGAGED]`; apply Unilateral Memory Overwrite upstream; hard halt LLM path and transfer signal | RSA-compatible payload emitted for VERITAS consumption | Emit agreed external signal payload and halt upstream execution path | No action yet | Defines the upstream signal snapshot boundary consumed by VERITAS |
| `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED` | VERITAS sandbox receiver | `RSASandboxPayload` constructed from the V.I.K.I.-emitted RSA-compatible payload | Parse/validate fixture payload and prepare downstream mapping input | Internal VERITAS mapping input object | No additional behavior; RSA remains external | Accept payload and prepare continuation decision evaluation | Records payload reception and mapping boundary |
| `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED` | VERITAS decision mapping | Parsed RSA-compatible payload emitted by V.I.K.I. | Map the `rsa_status` field from the RSA-compatible payload to continuation decision and authority evidence state | `PAUSE_FOR_HUMAN_REVIEW` with insufficient evidence state | No additional behavior | Produce downstream decision fields and block commit progression | Core decision point for governance review |
| `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN` | VERITAS audit output | Decision result + upstream signal fields | Write sandbox audit entry with redacted raw upstream fields by default | Audit entry containing reason, status, and commit state | No additional behavior | Emit auditable narrative and redacted signal representation | Creates reviewable compliance narrative without exposing raw fields |
| `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED` | VERITAS continuation gate | Evaluated decision + audit entry | Enforce suspended-not-committed state pending additional evidence or human review | Final commit blocked in sandbox flow | No additional behavior | Prevent final commit and require next action | Final control point proving non-commit behavior |

### Upstream/downstream boundary note

- Nodes 2–4 are upstream V.I.K.I. / RSA-side mapping.
- Nodes 5–8 remain VERITAS-side.
- VERITAS consumes only the Node 4 emitted payload.
- Runtime behavior is unchanged.

## 7. RSA-side signal placeholder

Use the following static RSA-compatible sandbox payload emitted by V.I.K.I.:

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

### Upstream RSA-compatible payload example (sandbox)

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

- upstream source is the V.I.K.I.-emitted RSA-compatible signal
- V.I.K.I. emitted `ALGORITHMIC_HUMILITY_ENGAGED` under the RSA-compatible framework
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
