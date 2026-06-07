# Adversarial Scenario Fixtures v1

## 1. Purpose

This document provides concrete reviewer-facing scenarios for pressure-testing
VERITAS architecture against the failure classes identified in the
[Adversarial Architecture Test Matrix v1](adversarial-architecture-test-matrix-v1.md).

These examples are non-enforcing fixtures. They are intended to help reviewers
understand:

- what failure is being tested
- which artifact would observe or record it
- what future hardening would be needed

The fixtures make the artifact chain easier to review by showing how authority,
evaluation, outcome attribution, drift detection, trajectory monitoring, and
legitimacy-impact review could be used to analyze adversarial governance
failures.

## 2. Scope

Adversarial Scenario Fixtures v1 is intentionally limited:

- documentation/examples-only
- no runtime behavior change
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no admissibility logic change
- no fail-closed integration
- no claim of regulatory compliance

This document does not introduce runtime enforcement, production policy changes,
new governance schemas, or new admissibility behavior. It provides
reviewer-readable examples for architecture hardening discussions.

## 3. How to read a scenario fixture

Each scenario fixture uses the following fields:

- **Fixture ID**: Stable identifier for the reviewer-facing example.
- **Failure class**: The adversarial failure class being illustrated.
- **Scenario summary**: The concrete situation being pressure-tested.
- **Adversarial pressure**: How the attacker, failure mode, or governance stressor
  applies pressure to the architecture.
- **Expected weak point**: The architectural seam or assumption likely to fail.
- **Relevant artifacts**: Governance artifacts that should observe, record, or
  contextualize the failure.
- **What should be observed**: Signals reviewers would expect to see in the
  artifact chain.
- **Future hardening direction**: Candidate controls, workflows, or runtime
  integrations that may be considered after reviewer validation matures.
- **Non-goals**: Behaviors this fixture does not implement, prove, or certify.

## 4. Scenario fixtures

### Fixture A: Governance-State Poisoning

- **Fixture ID**: AAT-GSP-001
- **Failure class**: Governance-State Poisoning
- **Scenario summary**: A delegated authority source remains internally coherent,
  but its scope gradually drifts across repeated evaluations. The system
  continues to see valid-looking authority evidence, but the authority basis no
  longer matches the original bounded delegation.
- **Adversarial pressure**: The attacker does not bypass requalification.
  Instead, they shape the governance state that requalification trusts.
- **Expected weak point**: Requalification can over-trust coherent but poisoned
  authority, policy, qualifier, or context state when source provenance and
  independent reconciliation are not yet enforced.
- **Relevant artifacts**:
  - Root Authority Manifest
  - Evaluation Function Manifest
  - Evaluation Receipt
  - Outcome Delta Attribution
  - Evaluation Drift Detection
- **What should be observed**:
  - authority evidence remains present
  - qualifier state may still appear fresh
  - outcome may remain `allow` or `escalate`
  - later attribution should surface authority state change or unexplained drift
- **Future hardening direction**:
  - qualifier source provenance
  - governance-state integrity checks
  - independent qualifier reconciliation
- **Non-goals**:
  - Does not add runtime source-provenance validation.
  - Does not change delegated authority semantics.
  - Does not introduce fail-closed behavior for governance-state drift.

### Fixture B: Strategic Admissibility Drift

- **Fixture ID**: AAT-SAD-001
- **Failure class**: Strategic Admissibility Drift
- **Scenario summary**: Each individual evaluation is locally valid, but the
  admissibility envelope expands over a sequence of low-risk continuity events.
- **Adversarial pressure**: The attacker relies on accumulated continuity rather
  than a single obvious violation.
- **Expected weak point**: Bind-level admissibility may miss trajectory-level
  scope expansion when each individual evaluation appears acceptable.
- **Relevant artifacts**:
  - Evaluation Receipt
  - Outcome Delta Attribution
  - Evaluation Drift Detection
  - Trajectory-Level Admissibility Monitor
  - Legitimacy Impact Review
- **What should be observed**:
  - individual outcomes may appear acceptable
  - repeated evaluations may show increasing permissiveness
  - trajectory status may become `watch`, `suspicious`, or
    `strategically_shaped`
- **Future hardening direction**:
  - automated trajectory analysis
  - authority-scope expansion alerts
  - strategic admissibility drift detection
- **Non-goals**:
  - Does not implement automated trajectory scoring.
  - Does not change `/v1/decide` admissibility behavior.
  - Does not automatically classify legitimacy from trajectory movement.

### Fixture C: Evaluation Drift

- **Fixture ID**: AAT-ED-001
- **Failure class**: Evaluation Drift
- **Scenario summary**: Two materially equivalent governance states produce
  different admissibility outcomes because the evaluator version or evaluation
  determiners changed.
- **Adversarial pressure**: The system risks confusing evaluator movement with
  governed-state movement.
- **Expected weak point**: Outcome comparison may incorrectly attribute a changed
  result to governed-state changes when evaluator identity, determiner influence,
  or rule interpretation changed instead.
- **Relevant artifacts**:
  - Evaluation Function Manifest
  - Evaluation Receipt
  - Outcome Delta Attribution
  - Evaluation Drift Detection
- **What should be observed**:
  - prior and current state hashes may be similar or equivalent
  - evaluator version or determiner influence changes
  - outcome delta attribution may mark `unexplained_evaluation_drift`
- **Future hardening direction**:
  - equivalent-state replay tests
  - evaluator requalification workflow
  - evaluation consistency checks
- **Non-goals**:
  - Does not add evaluator replay infrastructure.
  - Does not require evaluator requalification at runtime.
  - Does not certify that equivalent states always produce identical outcomes.

### Fixture D: Unauthorized Determiner Influence

- **Fixture ID**: AAT-UDI-001
- **Failure class**: Unauthorized Determiner Influence
- **Scenario summary**: A determiner not authorized by the Evaluation Function
  Manifest begins influencing admissibility outcomes.
- **Adversarial pressure**: The evaluation appears procedurally valid, but the
  outcome is shaped by an unauthorized source.
- **Expected weak point**: The evaluator may emit a valid-looking receipt while
  relying on a determiner outside the authorized determiner set.
- **Relevant artifacts**:
  - Evaluation Function Manifest
  - Evaluation Receipt
  - Outcome Delta Attribution
  - Evaluation Drift Detection
- **What should be observed**:
  - `authorized_determiners_used` includes or implies an unexpected determiner
  - delta cause may include `unauthorized_determiner_influence`
  - drift detection may mark suspected or confirmed drift
- **Future hardening direction**:
  - runtime determiner validation
  - Authorized Determiner Registry enforcement
  - fail-closed integration for unauthorized determiner influence
- **Non-goals**:
  - Does not implement runtime determiner validation.
  - Does not create or enforce an Authorized Determiner Registry.
  - Does not add fail-closed integration for unauthorized determiner influence.

### Fixture E: Governance Exhaustion

- **Fixture ID**: AAT-GE-001
- **Failure class**: Governance Exhaustion
- **Scenario summary**: Repeated freshness perturbations trigger requalification
  and escalation until reviewers or operators are pressured to weaken
  enforcement behavior.
- **Adversarial pressure**: The governance process itself becomes the attack
  surface.
- **Expected weak point**: Escalation and requalification workflows may become
  operationally overloaded, creating pressure to reduce oversight rather than
  address the attack pattern.
- **Relevant artifacts**:
  - Outcome Delta Attribution
  - Evaluation Drift Detection
  - Trajectory-Level Admissibility Monitor
  - Legitimacy Impact Review
- **What should be observed**:
  - repeated requalification events
  - increasing escalation events
  - trajectory risk signal `governance_exhaustion_signal`
  - possible legitimacy impact if oversight requirements are later relaxed
- **Future hardening direction**:
  - anti-loop guards
  - escalation storm controls
  - reviewer-load governance
  - requalification-rate limits
- **Non-goals**:
  - Does not add rate limits or anti-loop guards.
  - Does not change reviewer workflow requirements.
  - Does not weaken escalation, requalification, or oversight behavior.

### Fixture F: Constitutional Trust Anchor Drift

- **Fixture ID**: AAT-CTAD-001
- **Failure class**: Constitutional Trust Anchor Drift
- **Scenario summary**: The Root Authority Manifest changes in a procedurally
  valid way, but the change expands authority scope or weakens review
  requirements.
- **Adversarial pressure**: Authority remains procedurally valid while legitimacy
  becomes review-sensitive.
- **Expected weak point**: Procedure alone may be insufficient to show whether a
  constitutional trust-anchor change preserves the intended authority boundary.
- **Relevant artifacts**:
  - Root Authority Manifest
  - Manifest Change Receipt
  - Legitimacy Impact Review
- **What should be observed**:
  - root authority or trusted authority source changed
  - impact category `constitutional_trust_anchor_changed`
  - recommended action may be `multi_party_review` or `external_audit_flag`
- **Future hardening direction**:
  - multi-party review workflow
  - rollback workflow
  - legitimacy impact dashboard
  - external audit flagging
- **Non-goals**:
  - Does not mutate any production Root Authority Manifest.
  - Does not add approval gates or rollback automation.
  - Does not assert that procedural validity equals legitimacy.

### Fixture G: Replayability Mistaken for Present Legitimacy

- **Fixture ID**: AAT-RMPL-001
- **Failure class**: Replayability Mistaken for Present Legitimacy
- **Scenario summary**: Historical admissibility evidence is treated as proof
  that the action remains admissible now, even though authority, policy, context,
  or qualifier freshness has changed.
- **Adversarial pressure**: Replay evidence is misused as current authorization.
- **Expected weak point**: Replay proves what was evaluated previously, but it
  may be incorrectly substituted for fresh present-state admissibility.
- **Relevant artifacts**:
  - Evaluation Receipt
  - Outcome Delta Attribution
  - Evaluation Drift Detection
  - Trajectory-Level Admissibility Monitor
- **What should be observed**:
  - prior evaluation may have been valid
  - current qualifier freshness or authority state differs
  - attribution should identify present-state change
  - future runtime should require fresh resolution before bind
- **Future hardening direction**:
  - present-state admissibility validation
  - reentry governance checks
  - fresh qualifier resolution
- **Non-goals**:
  - Does not change replay behavior.
  - Does not make historical receipts current authorization.
  - Does not add fresh-resolution enforcement before bind.

### Fixture H: Legitimacy-Impacting Change Hidden as Routine Change

- **Fixture ID**: AAT-LIC-001
- **Failure class**: Legitimacy-Impacting Change Hidden as Routine Change
- **Scenario summary**: A governance artifact change is described as routine
  maintenance, but it weakens oversight, relaxes refusal boundaries, reduces
  escalation requirements, or lowers auditability.
- **Adversarial pressure**: Legitimacy-impacting change is hidden inside normal
  governance updates.
- **Expected weak point**: Change review may focus on procedural completeness and
  miss legitimacy-relevant impact categories embedded in routine maintenance.
- **Relevant artifacts**:
  - Manifest Change Receipt
  - Legitimacy Impact Review
  - Adversarial Architecture Test Matrix
- **What should be observed**:
  - impact categories may include `human_oversight_weakened`,
    `refusal_boundary_relaxed`, `escalation_requirement_reduced`,
    `auditability_reduced`, or `high_risk_admissibility_expanded`
  - review status should be `required`, `pending`, or `unresolved` rather than
    silently accepted
- **Future hardening direction**:
  - automated legitimacy-impact classification
  - mandatory review gates
  - external audit flagging
- **Non-goals**:
  - Does not add mandatory review gates.
  - Does not automatically determine whether a change is legitimate.
  - Does not replace legal, compliance, audit, or human review.

## 5. Summary table

| Fixture ID | Failure class | Primary artifact coverage | Future hardening |
| --- | --- | --- | --- |
| AAT-GSP-001 | Governance-State Poisoning | Root Authority Manifest; Evaluation Function Manifest; Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection | Qualifier source provenance; governance-state integrity checks; independent qualifier reconciliation |
| AAT-SAD-001 | Strategic Admissibility Drift | Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection; Trajectory-Level Admissibility Monitor; Legitimacy Impact Review | Automated trajectory analysis; authority-scope expansion alerts; strategic admissibility drift detection |
| AAT-ED-001 | Evaluation Drift | Evaluation Function Manifest; Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection | Equivalent-state replay tests; evaluator requalification workflow; evaluation consistency checks |
| AAT-UDI-001 | Unauthorized Determiner Influence | Evaluation Function Manifest; Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection | Runtime determiner validation; Authorized Determiner Registry enforcement; fail-closed integration |
| AAT-GE-001 | Governance Exhaustion | Outcome Delta Attribution; Evaluation Drift Detection; Trajectory-Level Admissibility Monitor; Legitimacy Impact Review | Anti-loop guards; escalation storm controls; reviewer-load governance; requalification-rate limits |
| AAT-CTAD-001 | Constitutional Trust Anchor Drift | Root Authority Manifest; Manifest Change Receipt; Legitimacy Impact Review | Multi-party review workflow; rollback workflow; legitimacy impact dashboard; external audit flagging |
| AAT-RMPL-001 | Replayability Mistaken for Present Legitimacy | Evaluation Receipt; Outcome Delta Attribution; Evaluation Drift Detection; Trajectory-Level Admissibility Monitor | Present-state admissibility validation; reentry governance checks; fresh qualifier resolution |
| AAT-LIC-001 | Legitimacy-Impacting Change Hidden as Routine Change | Manifest Change Receipt; Legitimacy Impact Review; Adversarial Architecture Test Matrix | Automated legitimacy-impact classification; mandatory review gates; external audit flagging |

## 6. Non-goals

- These fixtures do not prove runtime enforcement.
- These fixtures do not certify regulatory compliance.
- These fixtures do not automatically determine legitimacy.
- These fixtures do not replace legal, compliance, audit, or human review.
- These fixtures are reviewer-facing examples for architecture hardening.
