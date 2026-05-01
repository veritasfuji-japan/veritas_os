# Observe Mode Mission Control Walkthrough

## Purpose

This walkthrough explains how a dev-only `governance_observation` snapshot maps to Mission Control read-only display fields.

It does **not** enable Observe Mode runtime.

For the full proof pack index, see `docs/governance/observe_mode_proof_pack.md`.

## Generate a dev-only snapshot

```bash
python scripts/generate_observe_mode_demo_snapshot.py --out /tmp/observe_snapshot.json
```

## Validate the snapshot

```bash
python scripts/check_governance_observation.py /tmp/observe_snapshot.json
```

Expected output:

```text
governance_observation dry-run check: valid
file: /tmp/observe_snapshot.json
issues: 0
```

## Payload contract

The generated snapshot contains:

- `sample_kind`
- `governance_layer_snapshot`
- artifact ids:
  - `decision_id`
  - `bind_receipt_id`
  - `execution_intent_id`
- routing/context fields:
  - `participation_state`
  - `pre_bind_source`
  - `bind_reason_code`
  - `bind_failure_reason`
  - `failure_category`
  - `target_path`
  - `target_type`
  - `target_label`
  - `operator_surface`
  - `relevant_ui_href`
- `governance_observation`

## Governance observation fields

| Field | Example | Meaning |
|---|---|---|
| `policy_mode` | `observe` | Development/test observation semantics |
| `environment` | `development` | Non-production context |
| `would_have_blocked` | `true` | The action would have been blocked under enforcement |
| `would_have_blocked_reason` | `policy_violation:missing_authority_evidence` | Preserved would-be blocking reason |
| `effective_outcome` | `proceed` | Dev-only observed execution result |
| `observed_outcome` | `block` | Would-be enforcement outcome preserved for audit |
| `operator_warning` | `true` | Operator should see that this is not clean success |
| `audit_required` | `true` | Observation must remain auditable |

## Mission Control rendering contract

When `governance_observation` is present in the governance snapshot, Mission Control renders a read-only Governance observation section.

It should show:

- policy mode
- environment
- would-have-blocked status
- reason
- effective outcome
- observed outcome
- operator warning
- audit required

Important behavior:

- This is display-only.
- No runtime behavior changes.
- No Observe Mode switch is enabled.
- No production bypass is created.
- Missing `governance_observation` means the section is hidden.


## View the dev-only fixture route

Open the frontend route:

```text
/dev/mission-fixture
```

This route renders a static fixture through the Mission Control-style UI.

- It does not enable Observe Mode runtime.
- It does not call backend APIs.
- It does not create a production bypass.
- It is for local/dev/test inspection only.
- In production environments, the fixture viewer is disabled and does not render the static `governance_observation` fixture.
- Runtime behavior is unchanged and production remains fail-closed.


## Fixture copy integrity (root ↔ frontend)

`frontend/fixtures/governance_observation_live_snapshot.json` is a frontend-local dev-only copy of `fixtures/governance_observation_live_snapshot.json` (used because frontend bundling cannot import the repository-root fixture directly).

Drift detection is enforced with:

- `pytest -q veritas_os/tests/test_governance_observation_fixture_drift.py`
- `python scripts/check_governance_observation.py fixtures/governance_observation_live_snapshot.json`
- `python scripts/check_governance_observation.py frontend/fixtures/governance_observation_live_snapshot.json`

The drift test verifies alignment of:

- `governance_layer_snapshot.governance_observation`
- key artifact IDs (`decision_id`, `bind_receipt_id`, `execution_intent_id`)
- key routing/context fields (`participation_state`, `pre_bind_source`, `bind_reason_code`, `bind_failure_reason`, `failure_category`, `target_path`, `target_type`, `target_label`, `operator_surface`, `relevant_ui_href`)

This is fixture integrity validation only. Runtime behavior remains unchanged, Observe Mode runtime is not enabled, and production remains fail-closed.

## What this walkthrough proves

- Generated payload shape is understandable.
- CLI checker can validate the payload.
- Mission Control has a read-only display contract for these fields.
- Operators can distinguish dev-only observed proceed from would-be block.

## What this walkthrough does not prove

- It does not prove runtime Observe Mode is implemented.
- It does not prove production execution can proceed when blocked.
- It does not add an API endpoint.
- It does not load generated JSON into a live UI session.
- It does not replace runtime enforcement tests.

## Safety boundary

Development can move fast.
Production still fails closed.
Both modes remain auditable.
