# Controlled Execution Proof Architecture Freeze v1

Status: **FROZEN CONTROLLED PROOF SCOPE**

Freeze anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`  
Proof PR: #2215  
Required proof check: `reproducible-decision-to-effect-e2e`

Machine-readable contract:
[`docs/architecture/controlled-execution-proof-freeze-v1.json`](../../architecture/controlled-execution-proof-freeze-v1.json)

## 1. Purpose

This document freezes the **controlled current-head Decision-to-Effect sandbox
proof architecture** that was established before this freeze PR. The purpose of
the freeze is not to declare VERITAS production-ready. It is to create a stable
technical baseline so the next Large Consolidation Audit can remove duplication,
dead paths and unnecessary abstraction without silently changing the semantics
that were actually proven.

The freeze is intentionally narrow. It protects the proof path and its safety
meaning. It does not freeze every repository module, every future adapter, or
every possible production deployment.

## 2. Frozen proof chain

The frozen proof path is:

`POST /v1/decide`
→ verified CanonicalDecisionArtifact
→ deterministic promotion
→ native v2 authorization
→ PostgreSQL single-use consumption
→ current governance rechecks
→ exact sandbox action / endpoint / credential binding
→ credential resolution
→ durable dispatch intent
→ at-most-once certificate-validated TLS transport
→ synthetic sandbox event persistence
→ `EFFECT_UNKNOWN`
→ independent read-only reconciliation
→ durable reconciliation archive
→ BindReceipt / Outcome
→ crash recovery
→ machine-readable normal/fault proof artifacts.

Every stage remains linked to the original decision and exact execution intent.

## 3. Frozen safety semantics

The following meanings are part of the frozen contract:

1. Authorization issuance is **not** execution permission.
2. Single-use consumption is required before the sandbox execution attempt.
3. Fresh governance/risk/authority/approval conditions are rechecked before effect.
4. Dispatch intent is durably persisted before transport may begin.
5. `EFFECT_UNKNOWN` is a first-class uncertainty state, not failure.
6. Missing/404/unavailable lookup evidence never proves no effect.
7. Blind redispatch after possible effect is prohibited.
8. The same business event remains blocked while unresolved or confirmed.
9. Reconciliation is read-only and independently verifies persisted effect state.
10. BindReceipt / Outcome are retrospective evidence and create no new authority.
11. Crash recovery never resends the external effect.
12. Decision → authorization → consumption → effect → receipt/outcome lineage must
    remain verifiable.

## 4. Freeze anchor and proof evidence

The baseline is the main-branch merge commit for PR #2215:

`ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

Before merge, all 39 recorded checks passed, including the dedicated
`reproducible-decision-to-effect-e2e` workflow. That workflow generated
source-SHA-bound `report.json` and `evidence.json` runtime artifacts for both
normal and fault scenarios.

The freeze does not depend on copying one ephemeral CI report into source control.
Instead, the workflow, proof contract, source anchor and required safety semantics
are versioned. A later proof run must bind its own exact source SHA.

## 5. Changes permitted after freeze

The following classes are permitted without reopening the architecture, provided
existing contracts and proof tests remain green:

- security and correctness fixes;
- dependency maintenance;
- consolidation/refactoring that preserves observable contracts;
- dead/duplicate-path removal backed by evidence;
- test strengthening;
- documentation and external-review artifacts; and
- benchmark instrumentation that does not alter execution semantics.

A permitted change is not automatically safe. CI, targeted proof checks and human
review still apply.

## 6. Changes that reopen architecture

A new architecture decision is required before any change that:

- weakens fail-closed behavior;
- changes authorization or consumption meaning;
- changes `EFFECT_UNKNOWN`, retry or replacement-blocking semantics;
- widens credential/network authority;
- changes decision/authorization/receipt lineage;
- adds another external-effect path to this frozen proof claim;
- changes the definition of confirmed external effect;
- treats the controlled CI proof as production validation; or
- merges TrustLog exactly-once into this claim without separate proof.

Such a change is not prohibited forever. It simply cannot be smuggled through a
consolidation or maintenance PR.

## 7. Explicit non-claims

This architecture freeze does **not** establish:

- production readiness;
- real customer credentials;
- a real customer endpoint;
- independently operated production infrastructure;
- external UTC clock trust;
- TrustLog exactly-once publication; or
- regulatory approval/certification.

These remain separate future claims and must have their own evidence.

## 8. Next phase

After this freeze merges, the next roadmap step is the **Large Consolidation
Audit**. The audit should evaluate redundant implementations, duplicate verifiers,
unused abstractions, oversized schemas, similar test duplication, dead paths and
historical compatibility layers against this frozen contract.

Deletion and simplification are preferred over expansion when they preserve the
frozen proof.
