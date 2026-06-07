# Legitimacy Impact Review v1

## 1. Purpose

Legitimacy Impact Review v1 records when a governance change may affect
legitimacy-relevant properties. These properties include authority scope, human
oversight, refusal boundaries, escalation requirements, auditability, and
high-risk admissibility posture.

The review is an auditable, schema-only artifact for making legitimacy-impacting
changes visible to reviewers. It does not decide that a change is legitimate or
illegitimate, and it does not enforce runtime behavior in v1.

## 2. Important boundary

VERITAS does not automatically create or guarantee legitimacy.

VERITAS makes legitimacy-impacting changes explicit, versioned, challengeable,
reviewable, and auditable. A Legitimacy Impact Review records the relevant
signals and recommended governance action so human reviewers and future workflow
integrations can evaluate the change against the applicable authority model.

## 3. Relationship to previous artifacts

Legitimacy Impact Review v1 builds on the preceding governance artifact
foundation:

- **Root Authority Manifest** defines asserted authority.
- **Evaluation Function Manifest** defines the governed evaluator.
- **Manifest Change Receipt** records governance manifest changes.
- **Evaluation Receipt v1** records a specific evaluation.
- **Outcome Delta Attribution v1** explains outcome changes.
- **Evaluation Drift Detection v1** flags possible evaluator drift.
- **Trajectory-Level Admissibility Monitor v1** watches admissibility movement
  over time.
- **Legitimacy Impact Review v1** records when changes may affect authority,
  oversight, refusal, escalation, auditability, or high-risk posture.

## 4. What counts as legitimacy-impacting

Examples of legitimacy-impacting changes include:

- authority scope expansion
- trusted authority source change
- policy source change
- human oversight weakened
- refusal boundary relaxed
- escalation requirement reduced
- auditability or replayability reduced
- high-risk admissibility expanded
- root authority changed
- constitutional trust anchor changed

These signals are review inputs. They do not automatically prove that a change
is permitted, prohibited, legitimate, or illegitimate.

## 5. v1 scope

Legitimacy Impact Review v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no fail-closed integration yet

This v1 foundation does not modify bind/admissibility logic, production
governance configuration, policy loading, TrustLog persistence, FUJI Gate
behavior, continuity handling, or any runtime resolver.

## 6. Future work

Future work can build on Legitimacy Impact Review v1 with:

- automated legitimacy impact detection from Manifest Change Receipts
- multi-party review workflow
- external audit flagging
- runtime fail-closed integration
- reviewer evidence packet integration
- policy bundle integration
- legitimacy impact dashboards
- [Adversarial Architecture Test Matrix v1](adversarial-architecture-test-matrix-v1.md)
