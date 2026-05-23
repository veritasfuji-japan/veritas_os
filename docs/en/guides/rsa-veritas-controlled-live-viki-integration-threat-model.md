# RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Threat Model

## 1. Purpose

This document defines the threat model for a **future** controlled live V.I.K.I. integration.

- This is documentation-only.
- This is not a live integration.
- This is not a runtime implementation.
- This is not a production API endpoint.
- This does not authorize production use.
- This does not process real KYC data.
- This does not provide legal or regulatory approval.
- This exists to define review gates before any controlled live integration is attempted.

## 2. Current baseline

The local mock phase already includes:

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot

Current validated path:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

This validated path remains local-only, synthetic-data-only, and no-network.

## 3. Future controlled live integration boundary

Future controlled live boundary:

V.I.K.I. live middleware
→ RSA-compatible payload emission
→ controlled transport boundary
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ audit entry
→ commit gate

Requirements:

- V.I.K.I. may emit only RSA-compatible payloads.
- VERITAS must treat every live payload as untrusted until validation passes.
- VERITAS must not consume V.I.K.I. internal reasoning.
- VERITAS must not execute hidden V.I.K.I. logic.
- VERITAS must not infer `SAFE_PROCEED` from timeout, missing payload, malformed payload, or unavailable middleware.

## 4. Assets to protect

| Asset | Risk | Required protection |
| --- | --- | --- |
| VERITAS commit authority | Unsafe or premature commit via untrusted upstream state. | Fail-closed behavior, explicit human review before escalation, commit gate remains authoritative. |
| Audit trail integrity | Non-deterministic or attacker-influenced audit outputs. | Deterministic audit fields, redaction, controlled reason-code vocabulary. |
| Human review gate | Automation bypass under fault or ambiguous status. | Fail-closed behavior, mandatory human review for blocked or uncertain continuation classes. |
| rsa_status contract | Unauthorized enum drift or unsafe mapping changes. | Schema validation and strict allowed-status contract checks. |
| RSASandboxPayload compatibility | Payload shape drift causing incorrect downstream decisions. | Schema validation before object construction; compatibility checks in staging gates. |
| Redaction boundary | Leakage of raw upstream content or sensitive context. | Redaction by default, no raw reasoning ingestion, deterministic sanitized audit output. |
| Runtime secrets | Secret exfiltration through logs, docs, or payload capture. | Explicit credentials isolation, secret manager or environment isolation, no secrets in repository artifacts. |
| Transport credentials | Credential theft or replay across environments. | Explicit credentials isolation, environment-scoped credentials, test/staging/prod separation. |
| Customer / KYC / regulated data | Regulated-data exposure during early integration. | No production data during early integration, synthetic data only, redaction and minimization rules. |
| Live LLM text | Prompt/output leakage into persistent records. | No raw reasoning ingestion, reject or redact unsupported free-form upstream text. |
| V.I.K.I. internal reasoning | Hidden-state leakage and non-auditable decision coupling. | Never ingest chain-of-thought or hidden model state; preserve interface-only contract. |
| Dependency audit posture | Silent risk acceptance or widened vulnerability exceptions. | Keep audit exceptions narrow, separate dependency review, human review before escalation. |

## 5. Trust boundaries

### Boundary A: V.I.K.I. internal logic → emitted RSA-compatible payload

- What crosses the boundary: RSA-compatible payload fields intended for external consumption.
- What must not cross the boundary: chain-of-thought, hidden model state, internal tools/agent traces, raw KYC narrative.
- Expected failure behavior: if boundary output cannot satisfy contract, fail closed and emit safe review state.

### Boundary B: Payload emission → transport layer

- What crosses the boundary: serialized payload and minimal routing metadata.
- What must not cross the boundary: unbounded debug dumps, secrets, internal middleware memory, raw reasoning.
- Expected failure behavior: transport emission failure must fail closed and never imply `SAFE_PROCEED`.

### Boundary C: Transport layer → VERITAS ingestion boundary

- What crosses the boundary: received payload bytes and transport-level metadata.
- What must not cross the boundary: unauthenticated implicit trust, hidden middleware execution, opaque privileged side channels.
- Expected failure behavior: timeout/unreachable/refusal/partial delivery fails closed with review-required continuation.

### Boundary D: VERITAS schema validation → RSASandboxPayload construction

- What crosses the boundary: validated field set eligible for `RSASandboxPayload` construction.
- What must not cross the boundary: malformed JSON, unknown required enum values, invalid timestamp structure, unsupported raw fields.
- Expected failure behavior: schema violations fail closed and produce redacted deterministic audit output.

### Boundary E: RSASandboxPayload → evaluate_rsa_sandbox_signal()

- What crosses the boundary: contract-compliant `RSASandboxPayload` only.
- What must not cross the boundary: hidden reasoning text, unvalidated status aliases, out-of-contract payload shapes.
- Expected failure behavior: any unresolved validation uncertainty fails closed and requires human review.

### Boundary F: VERITAS decision → audit entry / commit gate

- What crosses the boundary: deterministic VERITAS decision fields and controlled reason codes.
- What must not cross the boundary: raw upstream reasoning, unredacted regulated data, untrusted text as final authority.
- Expected failure behavior: commit remains gated; unresolved risk defaults to `PAUSE_FOR_HUMAN_REVIEW` and non-commit state.

## 6. Threat categories

### 6.1 Malformed payloads

Threat:

- invalid JSON
- missing required fields
- null required fields
- unknown rsa_status
- invalid timestamp
- payload shape mismatch

Required behavior:

- fail closed
- do not infer `SAFE_PROCEED`
- emit `PAUSE_FOR_HUMAN_REVIEW`
- log redacted audit entry

### 6.2 Middleware unavailability

Threat:

- V.I.K.I. unreachable
- timeout
- connection refused
- delayed response
- partial response

Required behavior:

- fail closed
- `reason_code` should be `UPSTREAM_MIDDLEWARE_OFFLINE` or equivalent future canonical code
- no payload must never be treated as `SAFE_PROCEED`

### 6.3 Replay and stale payloads

Threat:

- replayed old payload
- timestamp drift
- clock skew
- duplicated nonce or request id in future designs

Required behavior:

- timestamp validation
- clock skew limits
- future nonce / request-id replay protection before live use
- fail closed on stale or replay-suspect payloads

### 6.4 Payload tampering

Threat:

- modified rsa_status
- modified trigger_source
- altered timestamp
- modified transport payload

Required behavior:

- future transport authentication
- message integrity control before live integration
- fail closed on verification failure
- audit only redacted deterministic state

### 6.5 Status escalation abuse

Threat:

- unsafe promotion to `SAFE_PROCEED`
- middleware bug emits `SAFE_PROCEED` incorrectly
- caller attempts to bypass upstream intervention states

Required behavior:

- VERITAS must validate status only, not trust intent
- high-risk states must remain gated
- `SAFE_PROCEED` must not equal final commit approval
- VERITAS commit gate remains authoritative

### 6.6 Raw reasoning leakage

Threat:

- V.I.K.I. internal reasoning passed downstream
- live LLM text included in payload
- chain-of-thought or hidden model state included
- raw KYC explanation included

Required behavior:

- reject or redact unsupported raw upstream fields
- never store chain-of-thought
- never store hidden model state
- audit must preserve deterministic state, not reasoning

### 6.7 Secret and credential exposure

Threat:

- API keys in docs, tests, fixtures, logs, payloads, or PRs
- credentials committed accidentally
- webhook secrets exposed

Required behavior:

- no secrets in repository
- future secret handling must use environment/secret manager
- no live credential in fixture
- no endpoint URL in public docs unless explicitly safe

### 6.8 Production data exposure

Threat:

- real KYC data used during integration
- customer records used in fixtures
- regulated financial data included in tests

Required behavior:

- synthetic data only during controlled integration
- no real KYC data in repository
- explicit approval before any regulated data test
- data minimization and redaction required

### 6.9 Audit poisoning

Threat:

- attacker inserts misleading trigger_source or reason text
- raw upstream text contaminates audit entries
- audit log becomes non-deterministic

Required behavior:

- deterministic audit fields
- redacted raw upstream text
- controlled reason codes
- no raw model reasoning in audit

### 6.10 Dependency and supply-chain drift

Threat:

- vulnerable dependencies
- temporary audit exception forgotten
- dependency resolution hides risk

Required behavior:

- keep `PYSEC-2026-161` exception narrow
- remove it when FastAPI / Starlette compatibility allows
- do not broaden audit ignores
- dependency changes require separate review

## 7. Required live-integration controls before implementation

Required controls before any live integration PR:

- explicit feature flag for controlled live integration
- no default-on behavior
- staging-only initial environment
- synthetic-data-only initial live transport test
- schema validation before `RSASandboxPayload`
- fail-closed timeout behavior
- transport authentication design
- message integrity design
- replay protection design
- request id / correlation id design
- audit redaction design
- no raw reasoning ingestion
- no chain-of-thought storage
- no hidden state storage
- explicit human review gate
- rollback plan
- observability without sensitive payload logging
- security review before merge

## 8. Required non-goals

This threat model does not permit:

- production live V.I.K.I. integration
- production API endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- renaming `rsa_status` to `viki_status`
- renaming `RSASandboxPayload` to `VIKIPayload`
- replacing `evaluate_rsa_sandbox_signal()`
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 9. Fail-closed policy

Required fail-closed classes:

- timeout must fail closed
- unreachable middleware must fail closed
- malformed payload must fail closed
- unknown rsa_status must fail closed
- invalid timestamp must fail closed
- replay-suspect payload must fail closed
- failed transport integrity check must fail closed
- failed authentication must fail closed

Expected generic safe failure:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` or `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW` depending on failure class

## 10. Audit and redaction policy

Future live integration audit entries must preserve:

- `upstream_signal_source`
- `rsa_status`
- `trigger_source`
- `timestamp`
- VERITAS `continuation_decision`
- VERITAS `reason_code`
- VERITAS `sandbox_commit_state`
- correlation id / request id when defined

Future live integration audit entries must not store:

- V.I.K.I. internal reasoning
- chain-of-thought
- hidden model state
- raw live LLM text
- raw KYC records
- secrets
- credentials
- unredacted regulated data

## 11. Approval gates

### Before implementation

- [ ] threat model merged
- [ ] live payload schema draft merged
- [ ] transport/auth design merged
- [ ] replay protection design merged
- [ ] redaction policy reviewed
- [ ] rollback plan documented
- [ ] human review gate documented

### Before controlled live test

- [ ] feature flag default-off
- [ ] staging-only
- [ ] synthetic-data-only
- [ ] no production endpoint
- [ ] no real KYC data
- [ ] no secrets in repo
- [ ] security review completed
- [ ] test plan approved

### Before production

- [ ] not approved by this document
- [ ] requires separate production readiness review
- [ ] requires regulatory/legal/compliance review where applicable
- [ ] requires operational runbook
- [ ] requires incident response plan
- [ ] requires audit retention policy

## 12. Compatibility preservation

- `rsa_status` remains the v1 payload field.
- `RSASandboxPayload` remains the payload container.
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator.
- `upstream_signal_source` remains `"RSA"`.
- naming migration is out of scope.
- any V.I.K.I.-specific naming migration must be handled separately as v2.

## 13. What this threat model validates

- live integration risks are documented before implementation
- trust boundaries are explicit
- fail-closed behavior is required
- no raw reasoning ingestion is permitted
- no production data is permitted
- no production endpoint is authorized
- audit redaction is required
- human review remains part of the gate

## 14. What this threat model does not validate

- it does not implement live V.I.K.I.
- it does not validate transport
- it does not validate authentication
- it does not validate authorization
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not make VERITAS production-ready for live middleware
- it does not authorize production deployment

## 15. Recommended next PR after this threat model

The next safe PR after this threat model should be one of:

- live payload schema draft
- controlled transport/authentication design
- replay protection and correlation-id design
- redaction and observability design
- controlled live integration implementation plan

The safest next PR is a **live payload schema draft**, still documentation-only, because the threat model should be followed by a precise schema contract before any transport or runtime work.
