# Observe Mode Developer Walkthrough

## Problem

Governance systems can slow development when missing evidence fields or policy issues immediately stop iteration. VERITAS must avoid becoming a system that is safe but too heavy for builders.

## Principle

Development can move fast.
Production still fails closed.
Both modes remain auditable.

## What Observe Mode foundation is

Observe Mode foundation is a semantics, schema, UI, fixture, and dry-run validation foundation for future development-time observation.

It is **not** a production bypass.

For an evidence-oriented proof pack covering files, tests, commands, and safety boundaries, see `docs/governance/observe_mode_proof_pack.md`.

## Current foundation

- Semantics doc: `docs/governance/observe_mode.md`
- Python schema: `GovernanceObservation`
- TypeScript type: `GovernanceObservation`
- Mission Control read-only display for received `governance_observation`
- BFF / adapter preservation tests for `governance_observation`
- Dev-only sample fixture: `fixtures/governance_observation_live_snapshot.json`
- Dry-run semantic evaluator: `veritas_os/governance/observation_evaluator.py`
- Test-only Observe Mode wrapper: `veritas_os/governance/observe_mode_wrapper.py`
- CLI checker: `scripts/check_governance_observation.py`
- Fixture validation script: `scripts/validate_governance_observation_fixture.sh`
- Dev-only generated observation path coverage: would-be outcome → wrapper-generated `GovernanceObservation` → semantic evaluator → snapshot fixture shape → Mission Control adapter/rendering tests

## What it does not do

- Does not enable Observe Mode runtime (this flow is still dev/test-only fixture validation)
- Does not connect the wrapper to production execution or bypass production enforcement
- Does not change policy engine behavior
- Does not add a UI toggle
- Does not generate production observation payloads
- Does not let production proceed when it would block
- Does not weaken fail-closed behavior

## Try it locally

Generate a dev-only snapshot (wrapper + dry-run evaluator):

```bash
python scripts/generate_observe_mode_demo_snapshot.py --out /tmp/observe_snapshot.json
```

Validate generated output with existing CLI checker:

```bash
python scripts/check_governance_observation.py /tmp/observe_snapshot.json
```

You can also emit to stdout:

```bash
python scripts/generate_observe_mode_demo_snapshot.py
```

This flow uses the test-only wrapper and dry-run evaluator, does not enable Observe Mode runtime, does not connect to production execution, and produces a Mission Control-style JSON payload for local inspection.

For how the generated snapshot maps to Mission Control read-only fields, see `docs/governance/observe_mode_mission_control_walkthrough.md`.

Single fixture check:

```bash
python scripts/check_governance_observation.py fixtures/governance_observation_live_snapshot.json
```

Expected output:

```text
governance_observation dry-run check: valid
file: fixtures/governance_observation_live_snapshot.json
issues: 0
```

Full validation:

```bash
pytest -q veritas_os/tests/test_observe_mode_wrapper.py
bash scripts/validate_governance_observation_fixture.sh
```

This script runs the Python evaluator tests, CLI tests, wrapper fixture-generation tests, CLI fixture check, adapter tests, and Mission Control read-only rendering tests.

## Safety rules

The dry-run evaluator rejects unsafe combinations and enforces evidence preservation rules:

- `environment=production` with `policy_mode=observe` is invalid
- `policy_mode=observe` requires `audit_required=true`
- `policy_mode=observe` requires `operator_warning=true`
- `would_have_blocked=true` requires a reason
- `would_have_blocked=true` requires an observed outcome
- `policy_mode=enforce` cannot proceed when `would_have_blocked=true`
- `policy_mode=off` requires audit

## Example payload

```json
{
  "governance_layer_snapshot": {
    "decision_id": "dec_observe_demo_001",
    "governance_observation": {
      "policy_mode": "observe",
      "environment": "development",
      "would_have_blocked": true,
      "would_have_blocked_reason": "policy_violation:missing_authority_evidence",
      "effective_outcome": "proceed",
      "observed_outcome": "block",
      "operator_warning": true,
      "audit_required": true
    }
  }
}
```

## How this appears in Mission Control

When a payload includes `governance_observation`, Mission Control renders a read-only Governance observation section. This only displays received fields and does not change runtime behavior.

## Future runtime rollout requirements

Any future runtime rollout must add explicit environment guards, operator-visible warnings, audit evidence preservation, and tests proving production remains fail-closed.
