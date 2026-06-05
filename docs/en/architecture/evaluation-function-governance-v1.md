# Evaluation Function Governance v1

## 1. Purpose

VERITAS should not treat the admissibility evaluator as an invisible runtime
mechanism. Bind decisions are important, but the function that decides whether a
regulated action is admissible is itself a governance artifact.

Evaluation Function Governance v1 adds schema-only foundations for making that
evaluation function explicit, versioned, challengeable, and auditable. The v1
artifacts identify the authority basis for governance changes, the governed
evaluation inputs and determiners, and the receipts that record manifest changes.

## 2. Problem

Admissibility governance has a recursion problem:

- VERITAS governs decisions.
- VERITAS must also govern the mechanism that produces those decisions.
- VERITAS must also govern the authority by which that mechanism can be changed.

If the evaluator changes without an explicit authority trail, then downstream
bind outcomes may appear legitimate merely because runtime code produced them.
That is not sufficient for an auditable decision OS. The evaluator needs a
recorded basis for its authorized inputs, rule versions, policy identities,
qualifier sources, and authority dependencies.

## 3. Key distinction

Evaluation Function Governance v1 separates three concepts:

- **Root Authority Manifest** governs authority. It defines the constitutional
  trust anchor for governance artifacts, including trusted authority sources,
  authorized manifest modifiers, approval requirements, and fail-closed
  conditions.
- **Evaluation Function Manifest** governs evaluation. It defines the
  admissibility evaluation function as a governed artifact, including authorized
  determiners, admissibility inputs, qualifier sources, policy identity, rule
  set version, evaluator version, refusal boundaries, and escalation resolver.
- **Manifest Change Receipt** records changes. It records who changed a
  governance manifest, what changed, why it changed, under what authority, with
  what approval evidence, and with what impact scope.

VERITAS does not automatically create legitimacy. VERITAS makes the asserted
authority basis explicit, versioned, challengeable, and auditable so reviewers
can inspect whether a decision, evaluator, or governance change rests on an
acceptable authority chain.

## 4. Evaluation consistency

If materially equivalent governance state produces different admissibility
outcomes, VERITAS should be able to attribute the delta to one or more explicit
causes:

- governed state changed
- policy identity changed
- rule version changed
- authority state changed
- qualifier freshness changed
- evaluator version changed
- unauthorized determiner influence
- unexplained evaluation drift

The v1 manifests do not perform this attribution at runtime. They provide the
schema foundation needed for future receipts and monitors to compare governed
evaluation state and explain why outcomes differ.

## 5. Trust anchor

The governance chain should terminate in an explicit constitutional trust anchor,
not in an implicit runtime assumption. The Root Authority Manifest exists to name
that anchor and the evidence sources that support it.

This does not mean VERITAS declares the anchor legitimate by itself. It means the
system records the asserted root authority so humans, auditors, and future
verification tools can challenge or accept the basis for governance changes.

## 6. v1 scope

Evaluation Function Governance v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance configuration mutation
- intended as a foundation for future hardening

These artifacts are documentation and validation-test foundations only. They do
not modify bind/admissibility logic, fail-closed behavior, policy loading,
TrustLog persistence, or production governance state.

## 7. Future work

Future hardening can build on these schema foundations with:

- Evaluation Receipt
- Outcome Delta Attribution
- Evaluation Drift Detection
- Trajectory-Level Admissibility Monitor
- Legitimacy Impact Review
- Runtime fail-closed integration
