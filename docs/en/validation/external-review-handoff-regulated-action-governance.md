# External Review Handoff Pack — Regulated Action Governance

## 1) Purpose

This document is an **external review handoff pack** for VERITAS OS regulated-action governance.

It summarizes the currently implemented Regulated Action Governance path and points reviewers to:

- source documents
- code artifacts
- tests
- quality gate evidence

This handoff pack is technical implementation evidence only. It is **not legal advice**, **not regulatory approval**, **not third-party certification**, and **not a standalone compliance claim**.

## 2) What VERITAS currently implements

Current implemented fact in repository scope:

- Decision Governance and Bind-Boundary Control Plane
- Regulated Action Governance Kernel
- Action Class Contract
- AML/KYC Customer Risk Escalation contract
- Authority Evidence artifact
- Runtime Authority Validation
- Admissibility Predicate evaluation
- Irreversible Commit Boundary Evaluator
- BindReceipt / BindSummary regulated-action fields
- AML/KYC deterministic regulated action path
- Mission Control / Bind Cockpit regulated-action display compatibility (as documented)
- Proof Pack / Quality Gate documentation
- Japanese summary documentation for reviewer routing

## 3) What VERITAS does not claim

VERITAS does **not** claim the following in this pack:

- legal advice
- regulatory approval
- third-party certification
- standalone compliance guarantee
- production validation against a real bank system
- connection to real customer data
- connection to real sanctions APIs
- execution of real account freeze, customer notification, or regulatory filing
- implementation/certification of any external governance framework

## 4) Reviewable regulated action path

AML/KYC Customer Risk Escalation path (reviewable sequence):

```text
AI-assisted risk detection
↓
Decision / execution intent
↓
Action Class Contract lookup
↓
Authority Evidence validation
↓
Runtime Authority Validation
↓
Admissibility Predicate evaluation
↓
Irreversible Commit Boundary
↓
BindReceipt / BindSummary enrichment
↓
commit / block / escalate / refuse
```

## 5) Scenario matrix

| Scenario | Requested action | Expected outcome | Review focus |
|---|---|---|---|
| Allowed internal escalation | `create_internal_risk_escalation` | `commit` | allowed scope + valid authority/evidence |
| Prohibited account freeze | `freeze_account` | `block` | prohibited scope |
| Prohibited customer notification | `notify_customer` | `block` | customer-affecting action blocked |
| Stale sanctions screening | stale evidence state | `escalate` or `block` | evidence freshness |
| Missing authority | no authority evidence | `block` | fail-closed authority |
| High irreversibility without approval | high impact action without required approval | `block` | human approval gate |
| Policy uncertainty | unresolved policy snapshot | `block` or `escalate` | policy identity uncertainty |

Notes:

- Current deterministic fixture expectation is `escalate` for stale-evidence scenario and `block` for policy uncertainty.
- Table keeps `escalate or block` where contract/predicate policy can conservatively vary while still fail-closed.

## 6) Authority Evidence vs Audit Log

- **Audit Log** records what happened.
- **Authority Evidence** proves why an action was authorized/admissible at bind time.
- Audit logs alone do not authorize commit.
- Authority Evidence must be validated, in-scope, freshness-checked, and hashable.
- Missing, expired, invalid, or indeterminate authority state is fail-closed (block/refuse).

## 7) Evidence artifacts for reviewers

- Action contract:
  - [`policies/action_contracts/aml_kyc_customer_risk_escalation.v1.yaml`](../../../policies/action_contracts/aml_kyc_customer_risk_escalation.v1.yaml)
- Runtime components:
  - [`veritas_os/governance/action_contracts.py`](../../../veritas_os/governance/action_contracts.py)
  - [`veritas_os/governance/authority_evidence.py`](../../../veritas_os/governance/authority_evidence.py)
  - [`veritas_os/governance/runtime_authority.py`](../../../veritas_os/governance/runtime_authority.py)
  - [`veritas_os/governance/commit_boundary.py`](../../../veritas_os/governance/commit_boundary.py)
  - [`veritas_os/policy/bind_artifacts.py`](../../../veritas_os/policy/bind_artifacts.py)
- Runner:
  - [`scripts/run_aml_kyc_regulated_action_path.py`](../../../scripts/run_aml_kyc_regulated_action_path.py)
- Governance tests:
  - [`tests/governance/test_action_class_contracts.py`](../../../tests/governance/test_action_class_contracts.py)
  - [`tests/governance/test_authority_evidence.py`](../../../tests/governance/test_authority_evidence.py)
  - [`tests/governance/test_runtime_authority_validation.py`](../../../tests/governance/test_runtime_authority_validation.py)
  - [`tests/governance/test_commit_boundary.py`](../../../tests/governance/test_commit_boundary.py)
  - [`tests/governance/test_aml_kyc_regulated_action_path.py`](../../../tests/governance/test_aml_kyc_regulated_action_path.py)
  - [`tests/governance/test_bind_receipt_regulated_action_fields.py`](../../../tests/governance/test_bind_receipt_regulated_action_fields.py)

## 8) Quality gate snapshot

Reference detail: [`docs/en/validation/regulated-action-governance-quality-gate.md`](regulated-action-governance-quality-gate.md).

Snapshot status from documented ledger (updated **2026-04-27 UTC**):

- **PASS**
  - Regulated action governance tests (`84 passed`)
  - AML/KYC deterministic fixture runner tests (`2 passed`)
  - Bilingual docs checker script
  - Bilingual docs checker pytest (`3 passed`)
  - Frontend governance compatibility tests (`12 passed`)
  - Frontend build
- **PASS with warnings**
  - Frontend lint (warnings noted as pre-existing / out of PR11 scope)
- **NOT RUN**
  - full repository test suite (`pytest -q`)
  - `ruff check` for markdown/docs context in that pass
- **NOT CONFIGURED**
  - `mypy` (no mypy configuration in `pyproject.toml`)
- **NOT VERIFIED**
  - latest GitHub Actions workflow state in local environment (`gh` unavailable in that pass)

## 9) Suggested external review questions

- Are the allowed and prohibited scopes clear enough for the regulated action path?
- Is Authority Evidence sufficiently distinct from Audit Logs?
- Does fail-closed behavior cover missing, stale, expired, and indeterminate authority?
- Are commit / block / escalate / refuse outcomes reviewable enough?
- Is the irreversible boundary defined clearly enough?
- Are human approval requirements sufficient for high-irreversibility actions?
- Are current synthetic AML/KYC scenarios adequate for first external review?
- What additional action classes are required before real pilot evaluation?
- What external authority-source integrations are required for real deployment?
- What evidence would an independent reviewer require before commercial PoC?

## 10) Known limitations

- Current action path is synthetic, deterministic, and side-effect-free.
- No real bank system integration.
- No real sanctions API integration.
- No real customer data integration.
- No real external regulatory filing execution.
- No production customer workflow validation.
- No third-party review evidence included yet.
- Broader action-class coverage remains roadmap.
- Full repository suite may not have been run unless listed in latest quality gate.
- Latest GitHub Actions state may not be verified locally unless explicitly listed in quality gate evidence.

## 11) Source documents

- [Regulated Action Governance Kernel](../architecture/regulated-action-governance-kernel.md)
- [Authority Evidence vs Audit Log](../architecture/authority-evidence-vs-audit-log.md)
- [AML/KYC Regulated Action Path (Use Case)](../use-cases/aml-kyc-regulated-action-path.md)
- [Regulated Action Governance Proof Pack](regulated-action-governance-proof-pack.md)
- [Regulated Action Governance Quality Gate](regulated-action-governance-quality-gate.md)
- [Regulated Action Governance Proof Pack 日本語要約](../../ja/validation/regulated-action-governance-proof-pack-summary.md)
- [Regulated Action Governance Quality Gate 日本語要約](../../ja/validation/regulated-action-governance-quality-gate-summary.md)
