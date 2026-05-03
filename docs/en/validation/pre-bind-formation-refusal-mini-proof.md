# Mini proof: covered `/v1/decide` pre-bind formation refusal

## What this proves

- On the covered `/v1/decide` path, non-promotable pre-bind formation lineage is structurally refused before ExecutionIntent construction.
- No ExecutionIntent or BindReceipt is created on the covered path.
- Operator recovery is `RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE`.
- Console displays the result as Formation Transition Refused.

## What this does not prove

- It does not prove enforcement across every bind-governed mutation path.
- It does not prove full production readiness.
- It does not prove all possible transformation-stability paths.
- It is a focused mini proof for the covered `/v1/decide` path.

## How to run / inspect

### Automated mini-proof test

```bash
pytest -q veritas_os/tests/test_pre_bind_formation_refusal_demo_fixture.py
```

### API demo example (manual)

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/decide" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  --data @examples/decide/pre_bind_formation_refusal_request.json
```

## Request fixture

- `examples/decide/pre_bind_formation_refusal_request.json`
- Uses a collapsed pre-bind participation signal (`closed/none/low/closed`) that maps to decision-shaping / collapsed state on the covered `/v1/decide` path.

## Expected response subset

- `examples/decide/pre_bind_formation_refusal_expected_subset.json`
- Stable subset only (no request_id/timestamps/dynamic IDs), including:
  - `lineage_promotability.promotability_status = non_promotable`
  - `transition_refusal.transition_status = structurally_refused`
  - `actionability_status = formation_transition_refused`
  - `business_decision = HOLD`
  - `next_action = RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE`
  - execution/bind fields are null

## Operator interpretation

When this mini proof passes, operators can interpret the covered `/v1/decide` outcome as: structural pre-bind formation refusal, no bind artifact creation, and required lineage reconstruction before any execution path can continue.

## Console behavior

Mission Control / Console should present this result as **Formation Transition Refused** (pre-bind refusal), not as a bind-time failure.
