# Regulated Action Governance Kernel

## Purpose

The Regulated Action Governance Kernel is an implementation layer that evaluates whether a selected action path may cross the bind boundary. It is designed for reviewable regulated action governance at bind time, using deterministic artifacts and fail-closed adjudication.

This document describes implementation primitives that exist in the current codebase. It does **not** claim legal compliance, regulatory approval, third-party certification, or guaranteed alignment with any external framework.

## Architecture

The kernel is composed of five runtime primitives plus bind receipt enrichment:

1. **Action Class Contract** (`ActionClassContract`) defining allowed/prohibited scope, required evidence, irreversibility profile, and escalation/refusal conditions.
2. **Authority Evidence** (`AuthorityEvidence`) carrying actor role/policy basis, source references, validity window, and verification status.
3. **Runtime Authority Validation** (`RuntimeAuthorityValidator`) evaluating deterministic predicates.
4. **Predicate Evaluation** (`PredicateResult`) producing pass/fail/stale/missing/indeterminate results and reasons.
5. **Irreversible Commit-Boundary Check** (`CommitBoundaryEvaluator`) resolving `commit | block | escalate | refuse`.
6. **BindReceipt enrichment** with regulated-action fields for downstream review.

## Relationship to existing bind-boundary control

The kernel does not replace the existing bind-boundary architecture. It enriches the existing `decision -> execution_intent -> bind_receipt` path with regulated-action governance artifacts and commit-boundary outcomes. The implementation is additive and keeps backward compatibility behavior for legacy bind summaries/receipts.

## Action Class Contract

Action-class contracts are machine-readable policy primitives that define:

- Action identity (`id`, `version`, `action_class`)
- Allowed and prohibited scopes
- Required evidence and freshness expectations
- Irreversibility profile
- Human approval rules
- Refusal/escalation conditions
- Default failure mode (`fail_closed`)

Current AML/KYC contract example: `policies/action_contracts/aml_kyc_customer_risk_escalation.v1.yaml`.

## Authority Evidence

Authority evidence is a first-class bind-time artifact, separate from audit logging. It includes:

- `authority_evidence_id`
- contract reference (`action_contract_id`, `action_contract_version`)
- actor identity/role and authority source references
- scope grants/limitations
- validity window (`issued_at`, `valid_from`, `valid_until`)
- verification status and optional failure reasons
- deterministic hash (`evidence_hash`)

Authority evidence is validated fail-closed for missing, expired, invalid, or indeterminate states.

## Runtime Authority Validation

Runtime validation evaluates deterministic predicates that include:

- contract presence/validity
- authority presence/validity/not-expired
- actor identity resolution
- requested scope admissibility
- prohibited scope absence
- required evidence presence
- evidence freshness state
- policy snapshot resolution
- irreversibility boundary definition
- human approval presence when required
- bind context validity

Output includes structured predicate sets and a recommended outcome (`commit`, `block`, `escalate`, `refuse`).

## Predicate Evaluation

Predicate statuses are explicit and reviewable:

- `pass`
- `fail`
- `stale`
- `missing`
- `indeterminate`

Outcome behavior is conservative:

- any `indeterminate` -> `refuse`
- stale evidence -> `escalate` when escalation conditions include stale evidence, otherwise `block`
- failed/missing predicates -> `block`
- all predicates pass -> `commit` (subject to admissible execution intent)

## Irreversible Commit Boundary

The commit boundary evaluator finalizes the crossing decision at bind time:

- `commit`: intent may cross boundary
- `block`: deny crossing due to failed/missing predicates
- `escalate`: require internal escalation workflow
- `refuse`: explicit refusal path for indeterminate authority or non-admissible state

This boundary is designed to be irreversible in the sense that real-world effect should not proceed unless the bind-time result permits commit.

## BindReceipt enrichment

Bind receipts and summaries are enriched with regulated-action fields, including:

- `action_contract_id`
- `authority_evidence_id`
- `authority_evidence_hash`
- `commit_boundary_result`
- `failed_predicates`, `stale_predicates`, `missing_predicates`
- `refusal_basis`, `escalation_basis`

This enables compact triage and deep review without requiring ad hoc log parsing.

## Fail-closed behavior

The kernel is intentionally fail-closed:

- missing contract/evidence/identity/policy context blocks or refuses
- expired or invalid authority blocks
- indeterminate authority refuses
- validator exceptions return fail status and block path
- prohibited scope requests are blocked

## Current limitations

Current implemented scope is intentionally limited:

- Coverage is currently demonstrated with deterministic AML/KYC regulated-action fixtures and related bind-time integration tests.
- Broader action-class coverage across all effect paths remains roadmap work.
- This kernel provides implementation primitives for reviewable governance, not legal or certification claims.
- Environment-specific operational controls (identity providers, enterprise workflow integration, organizational approval policy) remain deployment responsibilities.
