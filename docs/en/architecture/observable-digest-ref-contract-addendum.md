# Contract Addendum — `observable_digest_ref` Failure Codes and Remediation (VERITAS v1)

## Status

- Scope: VERITAS v1 WAT shadow / operator-facing governance path
- Surface impact: documentation and contract clarification only
- Runtime impact: none
- Default operator surface impact: none

This addendum preserves the current VERITAS v1 contract:

- `observable_digest_ref` is locator-first.
- Runtime decisions remain unchanged in v1.
- Failure codes are deterministic for callers and tooling.
- Remediation and SLA classes are documented without widening the default surface.
- Auditability stays append-only and drill-down oriented.

## 1. Locator-first contract

`observable_digest_ref` is a locator/reference to separate-store observable digest material.

It is not an inline digest payload alias.

The default contract is:

- callers provide a stable locator/reference before digest resolution;
- the boundary resolves the locator where resolution is available;
- the resolved digest material is validated against boundary expectations;
- mismatch states are explicit and deterministic;
- failure details remain in event-lane telemetry, audit detail, or expanded drill-down views.

The default `*_operator_summary` surface must not be widened by this addendum.

## 2. Failure-code contract

Failure codes are stable v1 contract vocabulary. They are designed for callers, tooling, audit queries, and operator drill-downs.

| Code | Name | Predicate | Remediation class | SLA window | Recommended remediation |
|---|---|---|---|---:|---|
| `FC01` | `LOCATOR_MISSING` | Required `observable_digest_ref` is absent or empty. | `ManualReview` | `86400` | Provide a valid separate-store locator and re-run boundary validation. |
| `FC02` | `LOCATOR_MALFORMED` | Locator is present but does not match the accepted locator shape or scheme. | `ManualReview` | `86400` | Correct the locator format/scheme and resubmit the request. |
| `FC03` | `RESOLUTION_FAILED` | Locator could not be resolved because the digest store or resolver is unavailable. | `Retryable` | `300` | Retry with backoff; escalate if the resolver remains unavailable beyond the SLA window. |
| `FC04` | `AUTHZ_DENIED` | Caller or service identity is not authorized to resolve the locator. | `ImmediateAction` | `3600` | Halt automated commit, review access policy, and require authorized operator approval before retry. |
| `FC05` | `DIGEST_MISMATCH` | Locator resolves successfully, but the resolved digest material does not match expected boundary material. | `ManualReview` | `86400` | Block commit, preserve resolved material in audit detail, and require reviewer approval before proceeding. |
| `FC06` | `BOUNDARY_VALIDATION_FAILURE` | Resolved digest material exists, but boundary validation fails for policy, schema, timestamp, replay, revocation, or admissibility reasons. | `ImmediateAction` | `3600` | Block the effect path, open an incident if behavioral risk exists, and attach mitigation plan. |
| `FC07` | `REPLAY_DUPLICATE` | The same locator or resolved digest appears within the anti-replay window. | `ImmediateAction` | `3600` | Treat as replay suspicion, halt automated commit, and require explicit review. |
| `FC08` | `STALE_DIGEST` | Resolved digest material is older than the allowed TTL or freshness threshold. | `ManualReview` | `86400` | Refresh digest material and re-run validation against the updated locator. |
| `FC09` | `SCHEMA_MISMATCH` | Input fails the v1 contract schema or required audit-entry shape. | `Deferred` | `86400` | Fix schema shape in the caller or adapter before retry. |
| `FC10` | `UNKNOWN_TRANSIENT` | Failure is transient but not yet classified by a more specific code. | `Retryable` | `60` | Retry with short backoff and create a follow-up classification task if repeated. |

## 3. Deterministic code assignment

Implementations must map observable error predicates to the canonical failure code deterministically.

Tooling must not derive failure codes from runtime jitter, free-form exception messages, or opaque downstream strings.

When multiple predicates apply, use this priority order:

1. `FC07` `REPLAY_DUPLICATE`
2. `FC05` `DIGEST_MISMATCH`
3. `FC06` `BOUNDARY_VALIDATION_FAILURE`
4. `FC04` `AUTHZ_DENIED`
5. `FC03` `RESOLUTION_FAILED`
6. `FC08` `STALE_DIGEST`
7. `FC02` `LOCATOR_MALFORMED`
8. `FC01` `LOCATOR_MISSING`
9. `FC09` `SCHEMA_MISMATCH`
10. `FC10` `UNKNOWN_TRANSIENT`

## 4. Unexpected digest material as dual-signal

When a locator resolves to unexpected digest material, the audit trail must preserve both sides:

- the locator that was supplied;
- the resolved digest material or compact digest reference;
- the expected validation target when safe to record;
- the validation result and failure code.

This is a forensic and auditability requirement. It does not change runtime decisions in v1.

## 5. Append-only audit-entry schema

Audit entries for this contract should be immutable, append-only, UTC timestamped, and drill-down oriented.

Minimum audit-entry shape:

```json
{
  "event_id": "00000000-0000-4000-8000-000000000000",
  "timestamp": "2026-04-29T00:00:00Z",
  "failure_code": "FC05",
  "failure_name": "DIGEST_MISMATCH",
  "locator": "separate_store://wat_observables/<wat_id>",
  "resolved_digest": "sha256:<resolved-material-digest>",
  "expected_digest": "sha256:<expected-material-digest>",
  "validation_result": "failed",
  "v1_schema_version": "observable_digest_ref_contract_v1",
  "remediation_class": "ManualReview",
  "sla_window_seconds": 86400,
  "caller_id_hash": "sha256:<caller-id-hash>",
  "actor": "api:decide_observer",
  "action_taken": "blocked_for_review",
  "revocation_vector": {
    "status": "active",
    "pending": false,
    "confirmed": false
  },
  "payload_summary": "compact non-sensitive payload summary",
  "remediation_attempts": []
}
```

Required fields:

- `event_id`
- `timestamp`
- `failure_code`
- `failure_name`
- `locator`
- `validation_result`
- `v1_schema_version`
- `remediation_class`
- `sla_window_seconds`
- `actor`
- `action_taken`

Optional fields may be omitted when unavailable or unsafe to record, but omission must not silently turn a failure into success.

## 6. Schema-only versus behavioral boundary

Schema-only fields are accepted, persisted, validated, or displayed, but do not trigger runtime side effects in v1.

Behavioral fields may trigger actions, state changes, human review, revocation, rollback, or downstream effects.

### Schema-only in v1

- `observable_digest_ref` contract metadata when no resolver is active
- `auto_escalate_confirmed_revocations`
- failure-code contract documentation
- remediation/SLA documentation
- audit-entry schema documentation

### Behavioral in v1

- confirmed revocation state when explicitly confirmed
- strict local validation result
- replay duplicate detection when active in verifier/event lane
- policy block / bind block / non-admissible verifier outcome

`auto_escalate_confirmed_revocations` remains schema-only for v1. It may become behavioral only in a future contract revision with a separate v2 trigger path.

## 7. v2 trigger path for auto-escalation

Future activation of `auto_escalate_confirmed_revocations` should require a separate v2 contract revision.

At minimum, that revision should define:

- confidence thresholds;
- quorum or multi-party approval requirements;
- verified replay evidence;
- required revocation-vector fields;
- rollback behavior;
- human-review escape hatch;
- acceptance tests proving no default-surface widening.

Until then, v1 must continue to treat the field as schema-only.

## 8. Operator-surface rule

This addendum does not add fields to the default operator summary.

Failure details, resolved locator material, remediation classes, SLA windows, and audit-entry payloads belong in:

- WAT event-lane telemetry;
- audit detail;
- expanded `*_operator_detail` views;
- external review / proof-pack documentation.

They do not belong in the default minimal `*_operator_summary` surface.

## 9. Release and testing expectations

Any implementation that changes `observable_digest_ref` behavior should include:

- unit tests mapping representative predicates to failure codes;
- audit-entry shape tests;
- immutability / append-only expectations;
- minimal-summary no-widening tests;
- staged rollout notes if a resolver becomes runtime-active;
- explicit owner and escalation path for behavioral activation.

## 10. Acceptance criteria

This addendum is satisfied when:

1. `observable_digest_ref` remains locator-first in documentation and implementation notes.
2. Failure codes are deterministic and documented.
3. Each failure code has a remediation class and SLA window.
4. Audit entries are append-only and drill-down oriented.
5. `auto_escalate_confirmed_revocations` remains schema-only for v1.
6. Runtime decisions remain unchanged in v1.
7. The default operator-facing surface remains unchanged.
