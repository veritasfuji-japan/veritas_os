# Evaluation Governance Overview v1

## 1. Purpose

Evaluation Governance is a reviewer-facing artifact chain that makes the
authority basis, evaluator definition, evaluation instance, outcome changes,
evaluator drift, trajectory movement, and legitimacy-impacting changes explicit
and auditable.

It helps reviewers answer:

- What authority was used?
- What evaluator was allowed to decide admissibility?
- What was evaluated?
- Why did the outcome change?
- Did the evaluator drift?
- Did admissibility expand over time?
- Did a governance change affect legitimacy-relevant properties?

## 2. Important boundary

VERITAS does not automatically create legitimacy. VERITAS does not certify
regulatory compliance. VERITAS does not claim these artifacts enforce governance
in v1. These artifacts are non-enforcing, reviewer-facing foundations.

Their purpose is to make governance evidence explicit, versioned,
challengeable, replayable, and auditable.

## 3. Artifact chain

| Artifact | Question it answers | Role |
| --- | --- | --- |
| Root Authority Manifest | What is the asserted authority / trust anchor? | Defines trusted authority sources and governance modification authority. |
| Evaluation Function Manifest | What evaluator is allowed to determine admissibility? | Defines policy identity, rule-set version, authorized determiners, inputs, qualifiers, refusal boundaries, and escalation resolver. |
| Manifest Change Receipt | What changed in a governance manifest? | Records governance manifest changes, approval evidence, and impact scope. |
| [Evaluation Receipt](evaluation-receipt-v1.md) | What happened in one evaluation? | Records evaluator version, policy, authority evidence, qualifiers, determiners, inputs, context, outcome, rationale codes, and hashes. |
| [Outcome Delta Attribution](outcome-delta-attribution-v1.md) | Why did an outcome change? | Compares evaluation receipts and attributes changes to state, policy, authority, qualifier, evaluator, determiner, or unexplained drift. |
| [Evaluation Drift Detection](evaluation-drift-detection-v1.md) | Did the evaluator drift? | Flags suspicious, unexplained, or non-deterministic evaluation behavior. |
| [Trajectory-Level Admissibility Monitor](trajectory-admissibility-monitor-v1.md) | Did admissibility expand over time? | Reviews repeated evaluations for strategic admissibility drift, scope expansion, and continuity-as-authorization risk. |
| [Legitimacy Impact Review](legitimacy-impact-review-v1.md) | Did a governance change affect legitimacy-relevant properties? | Surfaces changes involving authority scope, human oversight, refusal boundaries, escalation requirements, auditability, replayability, or high-risk admissibility posture. |

The Root Authority Manifest, Evaluation Function Manifest, and Manifest Change
Receipt schema foundations are introduced in
[Evaluation Function Governance v1](evaluation-function-governance-v1.md).

## 4. Failure classes covered

The Evaluation Governance artifact chain is intended to make the following
failure classes easier to inspect, challenge, and later automate against:

- **Governance-State Poisoning**: authority, policy, qualifier, or context state
  becomes poisoned while still appearing internally coherent.
- **Strategic Admissibility Drift**: repeated narrow approvals create a broader
  effective authorization over time.
- **Evaluation Drift**: materially equivalent governance state produces
  inconsistent or unexplained admissibility outcomes.
- **Unauthorized Determiner Influence**: an unapproved source starts shaping
  admissibility outcomes.
- **Governance Exhaustion**: reviewer or approval workflows become overloaded
  and start accepting weak evidence.
- **Constitutional Trust Anchor Drift**: the asserted authority basis changes in
  a procedurally valid but legitimacy-sensitive way.
- **Replayability Mistaken for Present Legitimacy**: a past replayable outcome is
  treated as current legitimacy even after authority, policy, or context changes.
- **Legitimacy-Impacting Change Hidden as Routine Change**: changes to oversight,
  refusal boundaries, auditability, replayability, or high-risk admissibility
  posture are framed as routine maintenance.

For the detailed adversarial mapping, see the
[Adversarial Architecture Test Matrix v1](adversarial-architecture-test-matrix-v1.md)
and [Adversarial Scenario Fixtures v1](adversarial-scenario-fixtures-v1.md).

## 5. Reviewer packet integration

Evaluation Governance artifacts can be attached to reviewer evidence packets
through optional `evaluation_governance_artifacts` references.

See:

- [Reviewer Evidence Packet v1](../demo/reviewer-evidence-packet.md)
- [Reviewer Evidence Packet example with Evaluation Governance attachments](../demo/examples/reviewer-evidence-packet-with-evaluation-governance-v1.json)
- [Evaluation Governance sample bundle v1](../demo/examples/evaluation-governance-sample-bundle-v1/)
- [Evaluation Governance offline-chain Reviewer Evidence Packet example](../demo/examples/evaluation-governance-chain-reviewer-packet-v1/)

The synthetic sample bundle can be validated locally with `scripts/demo/validate_evaluation_governance_sample_bundle.py`.

For a one-command synthetic reviewer demo, see [Evaluation Governance Reviewer Demo Quickstart v1](../demo/evaluation-governance-reviewer-demo-quickstart-v1.md).

In v1, this packet integration is optional, non-enforcing, and reference-only.
It does not require live runtime generation yet and does not change `/v1/decide`
behavior.

## 6. What this enables later

This one-page overview describes a foundation for later implementation work,
including:

1. Reviewer evidence packet generation that includes Evaluation Governance
   artifacts
2. Automated Outcome Delta Attribution
3. Automated Evaluation Drift Detection
4. Automated Trajectory-Level Admissibility analysis with the synthetic [helper example](../demo/examples/trajectory-admissibility-monitor-helper-v1/README.md)
5. Legitimacy Impact Review workflow
6. Runtime fail-closed integration after reviewer validation matures

## 7. Non-goals

- This document does not claim regulatory compliance.
- This document does not claim automatic legitimacy determination.
- This document does not change runtime behavior.
- This document does not certify governance correctness.
- This document does not replace human, legal, compliance, or audit review.
