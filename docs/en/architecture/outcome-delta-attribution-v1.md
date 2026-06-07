# Outcome Delta Attribution v1

## 1. Purpose

Outcome Delta Attribution v1 records why an admissibility outcome changed
between two Evaluation Receipts. It compares a prior evaluation instance with a
current evaluation instance and records whether the outcome changed, which
material deltas were observed, and whether any delta remains unresolved.

The artifact is designed for audit and review. It documents attribution claims
without deciding that the change was automatically legitimate.

## 2. Relationship to Evaluation Receipt

Evaluation Receipt v1 records one evaluation instance. It captures the governed
state, evaluator identity, policy identity, rule-set version, authority evidence,
qualifier state, determiners, admissibility inputs, consequence class, material
context, outcome, rationale codes, and hashes for that single evaluation.

Outcome Delta Attribution v1 compares two evaluation instances. It references a
prior Evaluation Receipt and a current Evaluation Receipt, records their hashes,
compares their outcomes, and lists the causes that explain the observed outcome
delta.

In short:

- **Evaluation Receipt** records what happened during one evaluation.
- **Outcome Delta Attribution** records why the result changed between two
  evaluations.

Evaluation Drift Detection v1 builds on this comparison by recording whether an
attributed or unattributed outcome delta suggests evaluator drift, unauthorized
determiner influence, unexplained evaluation behavior, or non-deterministically
governed evaluation. It remains non-enforcing in v1.

## 3. What the attribution captures

An Outcome Delta Attribution captures:

- prior and current Evaluation Receipt references
- prior and current Evaluation Receipt hashes
- prior and current admissibility outcomes
- whether the admissibility outcome changed
- delta causes and supporting evidence references
- attribution summary
- attribution confidence
- unresolved delta status
- recommended governance action
- attribution hash for later audit comparison

These fields make the comparison inspectable while preserving the distinction
between an attributed change and a governance-approved change.

## 4. Evaluation consistency

Outcome Delta Attribution supports evaluation consistency by separating outcome
changes that may be explained by governed causes from changes that require
review. In particular, it can distinguish:

- legitimate state evolution
- policy, rule, or authority change
- qualifier freshness change
- consequence class change
- evaluator version change
- authorized determiner change
- unauthorized determiner influence
- unexplained evaluation drift

This separation helps reviewers identify whether an outcome delta is plausibly
attributable to governed state, policy identity, rule-set version, authority
state, qualifier freshness, consequence classification, evaluator version, or
other recorded causes.

## 5. v1 scope

Outcome Delta Attribution v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no fail-closed integration yet

This v1 foundation does not modify bind/admissibility logic, production
governance configuration, policy loading, TrustLog persistence, FUJI Gate
behavior, or any runtime resolver.

## 6. Future work

Future work can build on Outcome Delta Attribution v1 with:

- Evaluation Drift Detection
- Trajectory-Level Admissibility Monitor
- Legitimacy Impact Review
- Runtime fail-closed integration
- Automated comparison from live Evaluation Receipts
- [Adversarial Architecture Test Matrix v1](adversarial-architecture-test-matrix-v1.md)
