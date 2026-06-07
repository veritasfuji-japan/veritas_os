# Adversarial Architecture Test Matrix v1

## 1. Purpose

This document turns the Evaluation Governance artifact chain into adversarial
pressure-test categories for reviewer-facing architecture hardening. It uses the
schema-only governance artifacts introduced across the governance-hardening
sequence to identify where adversarial pressure can break authority, evaluation,
outcome attribution, drift analysis, trajectory monitoring, or legitimacy-impact
review.

The goal is not only to identify vulnerabilities. The goal is also to identify
which failures force new governance primitives to exist, so future hardening can
be reviewed as an explicit architecture response rather than an implicit runtime
assumption.

## 2. Scope

Adversarial Architecture Test Matrix v1 is intentionally limited:

- documentation-only
- non-enforcing
- no runtime behavior change
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance configuration change
- no admissibility logic change
- no fail-closed behavior change
- intended for reviewer-facing architecture hardening

This document does not introduce runtime enforcement, production policy changes,
or new governance schemas. It organizes existing schema-only foundations into a
review matrix for future test design and architecture review.

## 3. Artifact chain

The current Evaluation Governance artifact chain is:

1. **Root Authority Manifest**
   Defines the constitutional trust anchor and asserted authority basis for the
   governance chain.
2. **Evaluation Function Manifest**
   Defines the governed admissibility evaluator, including authorized inputs,
   determiners, policy identity, rule versions, and authority dependencies.
3. **Manifest Change Receipt**
   Records changes to governance manifests, including change rationale,
   authority basis, approval evidence, and impact scope.
4. **Evaluation Receipt**
   Records a specific admissibility evaluation instance for replay, comparison,
   attribution, and audit.
5. **Outcome Delta Attribution**
   Explains why outcomes changed between evaluation receipts and records whether
   the delta remains unresolved.
6. **Evaluation Drift Detection**
   Flags unexplained or suspicious evaluator movement, including possible
   evaluator drift, unauthorized determiner influence, or non-deterministic
   evaluation behavior.
7. **Trajectory-Level Admissibility Monitor**
   Watches admissibility movement across repeated evaluations to surface
   trajectory-level scope expansion that may not be visible at a single bind.
8. **Legitimacy Impact Review**
   Records changes that may affect legitimacy-relevant properties such as
   authority scope, oversight, refusal boundaries, escalation, auditability, or
   high-risk posture.

## 4. Core adversarial failure classes

| Failure class | Attack / pressure scenario | What breaks | Existing artifact coverage | Missing / future governance primitive | Suggested future hardening |
| --- | --- | --- | --- | --- | --- |
| A. Governance-State Poisoning | Governance inputs drift or become indirectly shaped while appearing internally coherent. | Requalification may trust poisoned authority, policy, qualifier, or context state. | Root Authority Manifest; Evaluation Function Manifest; Evaluation Receipt. | Qualifier source provenance; governance-state integrity checks; independent qualifier reconciliation. | Add qualifier source provenance, governance-state integrity checks, and independent qualifier reconciliation workflows. |
| B. Strategic Admissibility Drift | Each evaluation appears locally valid, but repeated continuity events gradually expand the admissibility envelope. | Bind-level admissibility cannot see trajectory-level scope expansion. | Trajectory-Level Admissibility Monitor. | Automated trajectory analysis; strategic admissibility drift detection; authority-scope expansion alerts. | Add automated trajectory analysis, strategic admissibility drift detection, and authority-scope expansion alerts. |
| C. Evaluation Drift | Materially equivalent governance state produces different outcomes because the evaluator or determiners changed. | System may confuse governed-state movement with evaluator movement. | Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection. | Evaluator requalification workflow; equivalent-state replay tests; evaluation consistency checks. | Add evaluator requalification workflow, equivalent-state replay tests, and evaluation consistency checks. |
| D. Unauthorized Determiner Influence | An unapproved determiner begins influencing admissibility outcomes. | Evaluation appears valid but is shaped by an unauthorized source. | Evaluation Function Manifest; Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection. | Authorized Determiner Registry enforcement; runtime determiner validation. | Add Authorized Determiner Registry enforcement and runtime determiner validation after reviewer validation matures. |
| E. Governance Exhaustion | Repeated freshness perturbations trigger requalification and escalation until reviewers or operators weaken enforcement behavior. | The governance process itself becomes an attack surface. | Trajectory-Level Admissibility Monitor; Legitimacy Impact Review. | Anti-loop guards; escalation storm controls; reviewer-load governance; requalification-rate limits. | Add anti-loop guards, escalation storm controls, reviewer-load governance, and requalification-rate limits. |
| F. Constitutional Trust Anchor Drift | The Root Authority Manifest or constitutional trust anchor changes in a way that is procedurally valid but legitimacy-questionable. | Authority may remain procedurally valid while legitimacy becomes review-sensitive. | Root Authority Manifest; Manifest Change Receipt; Legitimacy Impact Review. | Multi-party review; external audit flagging; legitimacy impact dashboards; rollback workflows. | Add multi-party review, external audit flagging, legitimacy impact dashboards, and rollback workflows. |
| G. Replayability Mistaken for Present Legitimacy | Historical admissibility evidence is treated as proof of current admissibility. | Replay proves what was admissible then, not what is admissible now. | Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection. | Fresh qualifier resolution; reentry governance checks; present-state admissibility validation. | Add fresh qualifier resolution, reentry governance checks, and present-state admissibility validation. |
| H. Legitimacy-Impacting Change Hidden as Routine Change | A governance change relaxes oversight, refusal boundaries, auditability, or high-risk controls while being framed as routine maintenance. | Legitimacy-relevant changes are not surfaced for review. | Manifest Change Receipt; Legitimacy Impact Review. | Automated legitimacy-impact classification; mandatory review gates. | Add automated legitimacy-impact classification and mandatory review gates. |

## 5. Key architectural principles

- VERITAS does not automatically create legitimacy.
- VERITAS makes authority, evaluation, outcome change, drift, trajectory
  movement, and legitimacy-impacting changes explicit and auditable.
- Historical admissibility is replayable; present admissibility must be freshly
  resolved.
- Bind-level admissibility is necessary but not sufficient for trajectory-level
  governance.
- Evaluation consistency is required to distinguish state drift from evaluator
  drift.
- The governance chain should terminate in an explicit constitutional trust
  anchor, not an implicit runtime assumption.
- Legitimacy-impacting changes should be reviewable, not hidden as normal
  runtime behavior.

## 6. Future implementation path

See [Adversarial Scenario Fixtures v1](adversarial-scenario-fixtures-v1.md)
for reviewer-facing examples that instantiate these failure classes.

Suggested future PRs include:

1. Reviewer Evidence Packet integration for Evaluation Governance artifacts
2. Example adversarial scenario fixtures
3. Outcome Delta Attribution helper library
4. Evaluation Drift Detection helper library
5. Trajectory analysis prototype
6. Legitimacy Impact Review dashboard / report artifact
7. Runtime fail-closed integration after schema and reviewer validation mature

## 7. Non-goals

- This document does not claim regulatory compliance.
- This document does not claim automatic legitimacy determination.
- This document does not change runtime behavior.
- This document does not certify governance correctness.
- This document does not replace human, legal, compliance, or audit review.
