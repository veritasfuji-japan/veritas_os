# AML/KYC Regulated Action Path (Deterministic Use Case)

## Scope

This use-case documents the currently implemented deterministic AML/KYC regulated-action fixture path. It demonstrates bind-time governance behavior for selected scenarios and does not represent all production integrations.

## Scenario set (implemented)

Fixture scenarios are defined in:

- `veritas_os/sample_data/governance/aml_kyc_regulated_action_path/scenarios.json`

Implemented scenario intent:

1. **Allowed internal escalation** -> expected `commit`
2. **Prohibited account freeze** -> expected `block`
3. **Prohibited customer notification** -> expected `block`
4. **Stale evidence scenario** -> expected `escalate`
5. **Missing authority scenario** -> expected `block`
6. **High irreversibility without human approval** -> expected `block`
7. **Policy uncertainty / unresolved snapshot** -> expected `block`

## Governance interpretation

### Allowed internal escalation

Internal AML risk escalation (e.g., creating an internal case/escalation) may commit only when scope is allowed, required evidence is present/fresh, and authority evidence validates.

### Prohibited account freeze

`freeze_account` is prohibited in the action contract and must be blocked at bind time.

### Prohibited customer notification

`notify_customer` is prohibited in the action contract and must be blocked at bind time.

### Stale evidence scenario

When required evidence freshness is stale and stale evidence is configured as an escalation condition, outcome is `escalate`.

### Missing authority scenario

When authority evidence is absent, runtime predicates fail/mark missing and outcome is fail-closed (`block`).

### High irreversibility + human approval requirement

When irreversibility is high and approval rules require human approval, missing approval causes fail-closed blocking.

## How to run fixture/script

From repository root:

```bash
python scripts/run_aml_kyc_regulated_action_path.py
```

Optional JSON export:

```bash
python scripts/run_aml_kyc_regulated_action_path.py \
  --output-json artifacts/aml_kyc_regulated_action_path_report.json
```

Optional custom fixture:

```bash
python scripts/run_aml_kyc_regulated_action_path.py \
  --input veritas_os/sample_data/governance/aml_kyc_regulated_action_path/scenarios.json
```

## Expected outputs

The script prints a JSON array where each scenario contains fields including:

- `scenario_name`
- `expected_outcome`
- `actual_outcome`
- `commit_boundary_result`
- `action_contract_id`
- `authority_evidence_id`
- `bind_receipt_id`
- predicate counters (`failed_predicate_count`, `stale_predicate_count`, `missing_predicate_count`)
- `refusal_basis` and `escalation_basis`

Reviewer expectation: `actual_outcome` should match `expected_outcome` for all deterministic fixture scenarios.

## Security and control warning

This fixture is synthetic and side-effect-free by design. It should not be interpreted as permission to perform customer-impacting actions in live systems without separately implemented operational controls and approvals.
