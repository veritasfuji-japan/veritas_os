# RSA ↔ VERITAS Live V.I.K.I. Integration Reviewer Checklist

- [Controlled live V.I.K.I. replay protection and correlation-id design（pre-live 必須 replay/correlation gate、documentation-only、runtime 変更なし、live integration なし）](./rsa-veritas-controlled-live-viki-replay-correlation-design.md)
- [Controlled live V.I.K.I. redaction and observability design（pre-live 必須 redaction/observability gate、documentation-only、runtime 変更なし、live integration なし）](./rsa-veritas-controlled-live-viki-redaction-observability-design.md)
## 英語正本

- [RSA ↔ VERITAS Live V.I.K.I. Integration Reviewer Checklist](../../en/guides/rsa-veritas-live-viki-integration-reviewer-checklist.md)

## 1. 目的

このチェックリストは、将来の live V.I.K.I. integration 提案をレビューするための文書です。

- このチェックリストは runtime implementation ではありません。
- このチェックリストは live V.I.K.I. middleware を接続しません。
- このチェックリストは、live adapter 作業の前段で適用する review gate です。
- このチェックリストは、Live V.I.K.I. Integration Design Note と併用してください。

参照先:

- [Live V.I.K.I. integration design note](./rsa-veritas-live-viki-integration-design-note.md)
- [Local V.I.K.I. mock ingestion receiver design（documentation-only）](./rsa-veritas-local-viki-mock-ingestion-receiver-design.md)
- [Local V.I.K.I. mock receiver test fixture plan（documentation-only / receiver 未実装 / tests 未実装 / production endpoint 追加なし）](./rsa-veritas-local-viki-mock-receiver-test-fixture-plan.md)
- [Sandbox reviewer index](./rsa-veritas-sandbox-reviewer-index.md)
- [Controlled live V.I.K.I. integration threat model (documentation-only pre-live gate)](./rsa-veritas-controlled-live-viki-integration-threat-model.md)
- [Controlled live V.I.K.I. payload schema draft（pre-live 必須 schema gate、documentation-only）](./rsa-veritas-controlled-live-viki-payload-schema-draft.md)
- [Controlled live V.I.K.I. transport authentication design（pre-live 必須 transport/auth gate、documentation-only）](./rsa-veritas-controlled-live-viki-transport-authentication-design.md)

## 2. Review status legend

- PASS: requirement is satisfied.
- FAIL: requirement is violated.
- NEEDS DESIGN: requirement is not yet specified.
- BLOCKER: issue must be resolved before implementation.
- NOT APPLICABLE: requirement does not apply to the reviewed proposal.

## 3. Boundary checklist

- [ ] RSA is treated only as the theoretical framework / underlying rule set.
- [ ] V.I.K.I. remains external to VERITAS.
- [ ] VERITAS consumes only emitted RSA-compatible payloads.
- [ ] VERITAS does not consume V.I.K.I. internal reasoning.
- [ ] VERITAS does not ingest hidden reasoning, chain-of-thought, or raw internal model state.
- [ ] VERITAS remains responsible only for downstream continuation decision, audit entry, and commit-state control.
- [ ] The live adapter does not bypass VERITAS boundary validation.

## 4. Compatibility contract checklist

- [ ] rsa_status remains unchanged for v1 compatibility.
- [ ] RSASandboxPayload remains the VERITAS-side receiver contract name.
- [ ] evaluate_rsa_sandbox_signal() remains the boundary evaluation entrypoint.
- [ ] upstream_signal_source = "RSA" remains a v1 compatibility fixture/source label unless a separate v2 migration is explicitly approved.
- [ ] No viki_status or VIKIPayload rename is introduced in the v1 live integration path.
- [ ] Any v2 naming migration is documented separately and not mixed into this v1 design.

## 5. Payload schema checklist

- [ ] Allowed rsa_status values are explicitly defined.
- [ ] Required fields are explicitly defined.
- [ ] Optional fields are explicitly defined.
- [ ] Unknown fields behavior is explicitly defined.
- [ ] Missing required fields fail closed.
- [ ] Malformed payloads fail closed.
- [ ] Unknown rsa_status values fail closed or map to a safe failure state.
- [ ] Timestamp validation behavior is defined.
- [ ] Schema versioning behavior is defined.
- [ ] Replay protection expectations are defined before live transport is added.

## 6. Audit and redaction checklist

- [ ] Audit entries preserve VERITAS continuation_decision.
- [ ] Audit entries preserve VERITAS reason_code.
- [ ] Raw upstream original_llm_intent remains redacted by default.
- [ ] Raw upstream rsa_action_taken remains redacted by default.
- [ ] Audit output does not expose V.I.K.I. internal reasoning.
- [ ] Audit output contains enough information for external review.
- [ ] Redaction behavior is tested or explicitly planned before live integration.

## 7. Failure-mode checklist

- [ ] Unknown rsa_status cannot proceed silently.
- [ ] Missing required fields cannot proceed silently.
- [ ] Invalid payload shape cannot proceed silently.
- [ ] Untrusted raw upstream content cannot enter audit output without redaction.
- [ ] Final commit cannot occur from an unvalidated live signal.
- [ ] Live integration fails closed when payload validity cannot be established.
- [ ] Operator-facing remediation or next-action guidance is defined for each failure class.

## 8. Security and privacy checklist

- [ ] No secrets are committed.
- [ ] No API keys are committed.
- [ ] No webhook URLs are committed.
- [ ] No production endpoints are committed.
- [ ] No credentials are committed.
- [ ] No real customer data is used.
- [ ] No financial account data is used.
- [ ] No medical data is used.
- [ ] No KYC documents are used.
- [ ] No regulated data is used.
- [ ] Synthetic data is used for all test examples.
- [ ] No live production workflow authority is introduced.

## 9. Environment gate checklist

- [ ] Phase 0 remains static sandbox only.
- [ ] Phase 1 is contract-only design.
- [ ] Phase 2 is local mock adapter only.
- [ ] Phase 3 controlled integration test requires explicit approval.
- [ ] Phase 4 production-readiness review is separate and out of scope.
- [ ] No phase is skipped.
- [ ] Moving between phases requires reviewer approval.
- [ ] Test-only environment is required before any controlled integration.
- [ ] Synthetic data is mandatory before any controlled integration.

## 10. Non-goals checklist

- [ ] The proposal does not claim production AML/KYC compliance.
- [ ] The proposal does not claim regulatory approval.
- [ ] The proposal does not claim third-party certification.
- [ ] The proposal does not provide legal advice.
- [ ] The proposal does not claim real-world transaction safety.
- [ ] The proposal does not introduce live V.I.K.I. connection in documentation-only PRs.
- [ ] The proposal does not change production runtime governance without a separate implementation PR.

## 11. Reviewer decision template

Reviewer decision:
- Status: PASS / FAIL / NEEDS DESIGN / BLOCKER / NOT APPLICABLE
- Reviewed artifact:
- Boundary concerns:
- Schema concerns:
- Audit/redaction concerns:
- Security/privacy concerns:
- Required follow-up:
- Approved next phase:
- Reviewer:
- Date:

## 12. このチェックリスト後の推奨 PR

このチェックリストのマージ後、次の安全な PR は次のいずれかです。

- local mock adapter design note
- local mock adapter test fixture plan
- live payload schema draft
- controlled integration threat model

design note と reviewer checklist のレビュー完了前に、live V.I.K.I. integration を実装してはいけません。
