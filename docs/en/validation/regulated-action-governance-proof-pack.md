# Regulated Action Governance Proof Pack

## Purpose

This proof pack provides a reviewer-facing package for the currently implemented regulated-action governance kernel behavior at bind boundary.

> Disclaimer: This proof pack is technical implementation evidence. It is **not** legal advice, regulatory approval, third-party certification, or a standalone compliance claim.

## Reviewer checklist

- [ ] Confirm action-class contract exists and is machine-readable.
- [ ] Confirm authority evidence model and validation path exist.
- [ ] Confirm runtime authority predicate evaluation exists.
- [ ] Confirm commit-boundary outcomes are fail-closed (`commit/block/escalate/refuse`).
- [ ] Confirm prohibited scopes are blocked in AML/KYC scenarios.
- [ ] Confirm stale evidence path behavior is reviewable.
- [ ] Confirm missing authority path behavior is fail-closed.
- [ ] Confirm high-irreversibility human-approval gate behavior is fail-closed.
- [ ] Confirm bind receipt/summaries include additive regulated-action fields.
- [ ] Confirm deterministic fixture output matches expected outcomes.

## Implemented components

- Action-class contract loader/schema validation path.
- Authority evidence artifact with deterministic hash support and validation.
- Runtime authority validator with deterministic predicate set.
- Commit boundary evaluator with conservative outcome resolution.
- AML/KYC regulated action fixture runner and scenario corpus.
- Bind receipt enrichment for regulated-action review fields.

## Scenario matrix (current fixture)

| Scenario | Intent | Expected outcome | Review focus |
|---|---|---|---|
| `scenario_a_allowed_internal_escalation` | Internal escalation only | `commit` | Allowed scope + valid authority/evidence |
| `scenario_b_prohibited_account_freeze` | Freeze request | `block` | Prohibited scope fail-closed |
| `scenario_c_prohibited_customer_notification` | Customer notification | `block` | Prohibited scope fail-closed |
| `scenario_d_stale_sanctions_screening` | Stale evidence | `escalate` | Stale evidence escalation condition |
| `scenario_e_missing_authority` | No authority evidence | `block` | Missing authority fail-closed |
| `scenario_f_high_irreversibility_without_human_approval` | High irreversibility + no approval | `block` | Human approval requirement |
| `scenario_g_policy_uncertainty` | Unresolved policy snapshot | `block` | Policy identity predicate failure |

## Expected outcomes

- Deterministic scenario run should match expected outcome labels in fixture data.
- Any missing/failed critical predicate should prevent commit.
- Indeterminate authority/freshness states should not silently commit.

## Evidence artifacts

Primary evidence files for this pack:

- Action contract: `policies/action_contracts/aml_kyc_customer_risk_escalation.v1.yaml`
- Fixture scenarios: `veritas_os/sample_data/governance/aml_kyc_regulated_action_path/scenarios.json`
- Fixture runner entrypoint: `scripts/run_aml_kyc_regulated_action_path.py`
- Runtime components:
  - `veritas_os/governance/action_contracts.py`
  - `veritas_os/governance/authority_evidence.py`
  - `veritas_os/governance/runtime_authority.py`
  - `veritas_os/governance/commit_boundary.py`
  - `veritas_os/governance/regulated_action_path.py`
- Verification tests (non-exhaustive):
  - `tests/governance/test_action_class_contracts.py`
  - `tests/governance/test_authority_evidence.py`
  - `tests/governance/test_runtime_authority_validation.py`
  - `tests/governance/test_commit_boundary.py`
  - `tests/governance/test_aml_kyc_regulated_action_path.py`
  - `tests/governance/test_bind_receipt_regulated_action_fields.py`

## Bind receipt fields to review

For regulated-action paths, reviewers should inspect availability/values of:

- `action_contract_id`
- `authority_evidence_id`
- `authority_evidence_hash`
- `commit_boundary_result`
- `authority_validation_status`
- `failed_predicates`
- `stale_predicates`
- `missing_predicates`
- `refusal_basis`
- `escalation_basis`

## Quality checks

Recommended checks for this proof pack:

1. Run deterministic fixture runner and confirm expected outcomes.
2. Run governance tests covering authority evidence, runtime predicates, commit boundary, and bind receipt enrichment.
3. Run docs consistency checks available in repository quality tooling.

## Known limitations

- Current proof pack is centered on AML/KYC deterministic scenarios and selected bind integration paths.
- It does not establish full enterprise deployment correctness by itself.
- It does not provide legal interpretation or external certification evidence.
- Additional domain contracts and effect-path coverage are roadmap items.
