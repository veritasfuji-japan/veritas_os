# Observable Digest Ref Contract Addendum (VERITAS v1)

## 1) Status

- **Scope:** VERITAS v1 WAT shadow / operator-facing governance path.
- **Surface impact:** Documentation and contract clarification only.
- **Runtime impact:** None.
- **Default operator surface impact:** None.

This addendum is normative for contract interpretation in v1 and intentionally preserves currently implemented runtime behavior.

## 2) Locator-first contract

For VERITAS v1, `observable_digest_ref` remains **locator-first**:

- `observable_digest_ref` is a locator/reference to separate-store observable digest material.
- It is **not** an alias for inline digest payloads.
- The caller supplies a stable locator/reference.
- The boundary resolves the locator when a resolver exists in the active deployment.
- Resolved digest material is validated against boundary expectations.
- Failure details remain in event-lane telemetry, audit detail, and expanded drill-down surfaces.
- Default `*_operator_summary` outputs remain minimal and must not be widened by this addendum.

`observable_digest` may continue as a transitional compatibility field where currently implemented, without changing the locator-first interpretation of `observable_digest_ref`.

## 3) Failure-code contract

Tooling and callers should receive deterministic failure categorization for locator resolution and digest validation handling.

| Code | Name | Predicate | Remediation class | SLA window | Recommended remediation |
|---|---|---|---|---:|---|
| FC01 | LOCATOR_MISSING | Required `observable_digest_ref` is absent or empty | ManualReview | 86400 | Provide a valid separate-store locator and re-run boundary validation |
| FC02 | LOCATOR_MALFORMED | Locator is present but not accepted as locator shape/scheme | ManualReview | 86400 | Correct locator format/scheme and resubmit |
| FC03 | RESOLUTION_FAILED | Locator could not be resolved because resolver/store is unavailable | Retryable | 300 | Retry with backoff; escalate if unavailable beyond SLA |
| FC04 | AUTHZ_DENIED | Caller/service identity is not authorized to resolve locator | ImmediateAction | 3600 | Halt automated commit, review access policy, require authorized approval |
| FC05 | DIGEST_MISMATCH | Locator resolves but digest material does not match expected boundary material | ManualReview | 86400 | Block commit, preserve resolved material in audit detail, require reviewer approval |
| FC06 | BOUNDARY_VALIDATION_FAILURE | Resolved digest exists but boundary validation fails | ImmediateAction | 3600 | Block effect path, open incident if behavioral risk exists, attach mitigation |
| FC07 | REPLAY_DUPLICATE | Same locator or resolved digest appears within anti-replay window | ImmediateAction | 3600 | Treat as replay suspicion and require explicit review |
| FC08 | STALE_DIGEST | Resolved digest is older than allowed TTL/freshness threshold | ManualReview | 86400 | Refresh digest material and re-run validation |
| FC09 | SCHEMA_MISMATCH | Input fails v1 contract schema or audit-entry shape | Deferred | 86400 | Fix schema shape in caller/adapter before retry |
| FC10 | UNKNOWN_TRANSIENT | Transient failure not yet classified | Retryable | 60 | Retry with short backoff and create follow-up classification task if repeated |

Deterministic handling guidance:

- Classify by predicate first, not by free-text runtime messages.
- Bind retry behavior to `Retryable` entries with bounded backoff.
- Bind block/escalation behavior to `ImmediateAction` and `ManualReview` entries.
- Preserve code stability (`FCxx` + `Name`) so downstream tooling can branch safely.

## 4) Deterministic assignment priority

When multiple predicates could apply, assignment must use a fixed priority. Tooling must not derive codes from opaque runtime text, timing jitter, or non-deterministic exception formatting.

Priority order:

1. `REPLAY_DUPLICATE`
2. `DIGEST_MISMATCH`
3. `BOUNDARY_VALIDATION_FAILURE`
4. `AUTHZ_DENIED`
5. `RESOLUTION_FAILED`
6. `STALE_DIGEST`
7. `LOCATOR_MALFORMED`
8. `LOCATOR_MISSING`
9. `SCHEMA_MISMATCH`
10. `UNKNOWN_TRANSIENT`

## 5) Unexpected digest material as dual-signal

If a locator resolves to unexpected digest material, v1 handling should emit a dual-signal in audit/drill-down artifacts:

- supplied locator
- resolved digest material (or compact digest reference)
- expected validation target (when safe to expose)
- validation result
- failure code

This dual-signal supports forensic reconstruction and reviewer accountability. It does **not** change runtime decision semantics in v1.

## 6) Append-only audit-entry schema

The following sample shape defines expected audit-entry fields for failure-oriented digest resolution/validation events:

```json
{
  "event_id": "evt_01J...",
  "timestamp": "2026-05-01T00:00:00Z",
  "failure_code": "FC05",
  "failure_name": "DIGEST_MISMATCH",
  "locator": "store://tenant-x/observable/abc",
  "resolved_digest": "sha256:...",
  "expected_digest": "sha256:...",
  "validation_result": "failed",
  "v1_schema_version": "1.0",
  "remediation_class": "ManualReview",
  "sla_window_seconds": 86400,
  "caller_id_hash": "sha256:...",
  "actor": "wat_boundary",
  "action_taken": "blocked_pending_review",
  "revocation_vector": {
    "confirmed": true,
    "source_count": 2,
    "compact": "rv:..."
  },
  "payload_summary": {
    "digest_bytes": 32,
    "locator_scheme": "store"
  },
  "remediation_attempts": 1
}
```

Requirements:

- Entries should be immutable and append-only.
- `timestamp` should be ISO8601 UTC.
- Optional fields may be omitted only when unavailable or unsafe to expose.
- Omission must not silently convert a failure condition into success semantics.

## 7) Schema-only vs behavioral boundary

### Schema-only in v1

- `observable_digest_ref` contract metadata when no resolver is active.
- `auto_escalate_confirmed_revocations`.
- Failure-code contract documentation.
- Remediation/SLA documentation.
- Audit-entry schema documentation.

### Behavioral in v1

- Confirmed revocation state when explicitly confirmed.
- Strict local validation result.
- Replay duplicate detection when active in verifier/event lane.
- Policy block / bind block / non-admissible verifier outcome.

`auto_escalate_confirmed_revocations` remains schema-only for v1 and may become behavioral only in a future v2 contract revision.

## 8) v2 trigger path for auto-escalation

Any future behavioral activation should require all of the following contract controls:

- confidence thresholds
- quorum or multi-party approval requirements
- verified replay evidence
- required revocation-vector fields
- rollback behavior
- human-review escape hatch
- acceptance tests proving no default-surface widening

Until those controls are explicitly implemented and released under a v2 contract revision, v1 keeps `auto_escalate_confirmed_revocations` schema-only.

## 9) Operator surface rule

This addendum does not add fields to default operator summary surfaces.

Extended failure/audit details belong in:

- WAT event-lane telemetry
- audit detail
- expanded `*_operator_detail`
- proof-pack or external review documentation

They do not belong in default minimal `*_operator_summary` outputs.

## 10) Release and testing expectations

For future implementation work that operationalizes this contract language:

- unit tests mapping representative predicates to failure codes
- audit-entry shape tests
- immutability/append-only expectations for audit records
- minimal-summary no-widening tests
- staged rollout notes if locator resolver behavior becomes runtime-active
- named owner/escalation path for behavioral activation

## 11) Acceptance criteria

This addendum is satisfied when all of the following are true:

- locator-first semantics remain intact
- failure codes are deterministic
- each code has remediation and SLA guidance
- audit entries are append-only and drill-down oriented
- `auto_escalate_confirmed_revocations` remains schema-only for v1
- runtime decisions remain unchanged
- default operator surface remains unchanged
