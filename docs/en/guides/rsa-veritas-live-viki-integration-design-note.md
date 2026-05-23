# RSA ↔ VERITAS Live V.I.K.I. Integration Design Note

- [Controlled live V.I.K.I. replay protection and correlation-id design (required pre-live replay/correlation gate, documentation-only; no runtime changes; no live integration)](./rsa-veritas-controlled-live-viki-replay-correlation-design.md)
## 1. Purpose

This document is a design note for a possible future live V.I.K.I. integration.

- This is not a runtime implementation.
- This is not a live middleware connection.
- This is not production AML/KYC compliance.
- This is a boundary and validation design note for future review.
- This design note should be reviewed together with the reviewer checklist.

Related documentation artifacts:

- [Local V.I.K.I. mock ingestion receiver design (Phase 2 local mock artifact, documentation-only)](./rsa-veritas-local-viki-mock-ingestion-receiver-design.md)
- [Live V.I.K.I. integration reviewer checklist](./rsa-veritas-live-viki-integration-reviewer-checklist.md)
- [Controlled live V.I.K.I. integration threat model (documentation-only pre-live gate)](./rsa-veritas-controlled-live-viki-integration-threat-model.md)
- [Controlled live V.I.K.I. payload schema draft (required pre-live schema gate, documentation-only)](./rsa-veritas-controlled-live-viki-payload-schema-draft.md)
- [Controlled live V.I.K.I. transport authentication design (required pre-live transport/auth gate, documentation-only)](./rsa-veritas-controlled-live-viki-transport-authentication-design.md)

## 2. Current static baseline

The static sandbox documentation set already includes:

- AML/KYC scenario map.
- E2E sandbox demo plan.
- E2E sandbox validation snapshot.
- Static fixture matrix.
- Sandbox reviewer index.
- SAFE_PROCEED validation snapshot.
- DENSITY_THROTTLED validation snapshot.
- ALGORITHMIC_HUMILITY_ENGAGED validation snapshot.
- DEFERRAL_ENGAGED validation snapshot.
- Live V.I.K.I. integration reviewer checklist (documentation-only review-gate artifact).

The static fixture ladder is now symmetrical:

- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

## 3. Boundary model

RSA:

- theoretical framework and underlying rule set.

V.I.K.I.:

- operational middleware.
- performs upstream behavioral/context checks.
- emits RSA-compatible upstream payloads.
- remains external to VERITAS.

VERITAS:

- consumes only the emitted payload.
- does not consume V.I.K.I. internal reasoning.
- maps the emitted payload to continuation decisions.
- emits audit entries.
- prevents unsafe final commit where applicable.

## 4. Compatibility contract

The following names remain stable in the v1 sandbox contract:

- rsa_status
- RSASandboxPayload
- evaluate_rsa_sandbox_signal()
- upstream_signal_source = "RSA"

Notes:

- upstream_signal_source = "RSA" remains a v1 compatibility fixture/source label.
- This label does not mean VERITAS consumes V.I.K.I. internal reasoning.
- A future live V.I.K.I. integration may emit RSA-compatible payloads into the same receiver contract.
- Any renaming such as viki_status or VIKIPayload should be considered a separate v2 migration and must not be mixed into the v1 live integration design.

## 5. Proposed live integration flow

V.I.K.I. runtime check
→ RSA-compatible upstream payload emitted
→ RSASandboxPayload validation at VERITAS boundary
→ evaluate_rsa_sandbox_signal(payload)
→ VERITAS continuation decision
→ audit entry
→ commit state decision

Additional constraints:

- VERITAS must only trust the emitted payload after schema validation.
- VERITAS must not ingest V.I.K.I. hidden reasoning, chain-of-thought, or raw internal model state.
- Any raw upstream fields that may contain sensitive intent/action data should remain redacted by default in audit output.

## 6. Phase gates before live connection

Phase 0: Current static sandbox

- Static fixtures only.
- No network connection.
- No live middleware.
- No real regulated data.

Phase 1: Contract-only live adapter design

- Define payload schema boundaries.
- Define allowed enum values.
- Define redaction expectations.
- Define error handling and reject behavior.
- No runtime connection yet.

Phase 2: Local mock adapter

- Local mock V.I.K.I. emitter.
- Deterministic test payloads.
- No external network.
- No secrets.
- No real data.

Phase 3: Controlled integration test

- Explicitly gated.
- Test-only environment.
- Synthetic data only.
- No production commit authority.
- Full audit output review.

Phase 4: Future production-readiness review

- Separate review.
- Separate security model.
- Separate compliance review.
- Separate operational approval.
- Not covered by this design note.

## 7. Failure and reject behavior

- Unknown rsa_status must be rejected or mapped to safe failure behavior.
- Malformed payloads must not proceed.
- Missing required fields must not proceed.
- Invalid timestamps should be recorded or rejected according to future schema rules.
- Untrusted raw upstream content must not be included in audit output without redaction.
- Live integration must fail closed when payload validity cannot be established.
- Final commit must not occur from an unvalidated live signal.

## 8. Audit and redaction expectations

- Audit entries should preserve the VERITAS decision and reason code.
- Raw upstream intent/action fields should remain redacted by default.
- The audit entry should show enough information for review without exposing V.I.K.I. internal reasoning.
- The boundary should remain reviewable by external auditors.

## 9. Security and privacy constraints

- No secrets in docs.
- No API keys.
- No webhook URLs.
- No production endpoints.
- No real customer data.
- No financial account data.
- No medical data.
- No KYC documents.
- No regulated data.
- No live production workflow authority.

## 10. What this design note validates

- The intended live integration boundary is documented.
- The static sandbox artifacts now have a path toward a future live adapter.
- The v1 compatibility contract remains stable.
- VERITAS remains downstream-only.
- V.I.K.I. remains external.
- Live integration is explicitly gated and not silently introduced.

## 11. What this design note does not validate

- It does not connect live V.I.K.I. middleware.
- It does not validate V.I.K.I. internal reasoning.
- It does not validate network transport.
- It does not validate authentication or authorization.
- It does not validate production compliance.
- It does not validate real AML/KYC use.
- It does not provide regulatory approval.
- It does not provide legal advice.
- It does not change production runtime behavior.

## 12. Open questions before implementation

- What exact live payload transport would be used?
- How would payload authenticity be verified?
- How would replay protection work?
- How would schema versioning be handled?
- Should v1 keep rsa_status permanently or introduce v2 viki_status later?
- What audit fields are mandatory for live review?
- What failure mode is required for each malformed payload class?
- What environment gating is required before controlled integration tests?
- Who approves moving from local mock adapter to controlled integration test?

## 13. Recommended next PR after this note

After this design note is merged, the next safe PR should be either:

- a reviewer checklist for the live integration design, or
- a local mock adapter design note.

Do not implement live V.I.K.I. integration until the design note and checklist are reviewed.
