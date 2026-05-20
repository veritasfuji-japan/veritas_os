# DecideResponse v2 Architecture Plan (H-3)

## Status

- **Type**: Architecture proposal only.
- **Implementation status**: Not implemented.
- **Scope of this PR**: Documentation only; no runtime behavior change.

## Problem Statement

`DecideResponse` has grown into a broad mixed-surface payload. The current shape combines concerns with different stability and audience requirements:

- user-facing decision output;
- governance and audit metadata;
- runtime diagnostics;
- compatibility fields for legacy callers;
- evidence and replay-oriented metadata.

This coupling increases risk and cost for:

- public API stability;
- external documentation clarity;
- strict schema validation;
- future SDK generation and versioning.

The architectural issue is not that these data classes exist, but that they are not cleanly separated into explicit contracts.

## Design Goals

DecideResponse v2 should provide:

1. A stable public response contract with explicit schema versioning.
2. Explicit governance metadata boundaries (separate from user-facing output).
3. Replay and audit compatibility that preserves TrustLog/replay usefulness.
4. Backward-compatible migration with v1 remaining functional.
5. Strict separation between user-facing result data and internal diagnostics.
6. No breaking change to v1 during initial rollout.
7. No runtime behavior change in this planning PR.

## Proposed v2 Shape (Draft)

The following is a proposal, not a final schema:

```json
{
  "schema_version": "decide_response.v2",
  "decision": {
    "answer": "...",
    "alternatives": [],
    "recommendation": {},
    "confidence": null
  },
  "governance": {
    "fuji_decision": {},
    "policy_result": {},
    "enforcement": {},
    "risk": {}
  },
  "evidence": {
    "items": [],
    "retrieval": {},
    "citations": []
  },
  "audit": {
    "request_id": "...",
    "trace_id": "...",
    "trustlog_ref": null,
    "replay_ref": null
  },
  "diagnostics": {
    "warnings": [],
    "degraded_modes": [],
    "tool_status": {}
  },
  "compat": {
    "v1_fields": {},
    "migration_notes": []
  }
}
```

### Enforcement Response Examples (non-normative)

Example 1 — FUJI BLOCK:

```json
{
  "schema_version": "decide_response.v2",
  "decision": {
    "answer": null,
    "alternatives": [],
    "recommendation": null,
    "confidence": null
  },
  "governance": {
    "fuji_decision": {},
    "policy_result": {},
    "enforcement": {
      "action": "BLOCK",
      "reason": "Policy violation: risk level exceeded configured threshold."
    },
    "risk": {}
  },
  "evidence": {
    "items": [],
    "retrieval": {},
    "citations": []
  },
  "audit": {
    "request_id": "...",
    "trace_id": "...",
    "trustlog_ref": "<non-null: block event MUST be logged>",
    "replay_ref": null
  },
  "diagnostics": {
    "warnings": [],
    "degraded_modes": [],
    "tool_status": {}
  },
  "compat": {
    "v1_fields": {},
    "migration_notes": []
  }
}
```

Example 2 — FUJI DEFER:

```json
{
  "schema_version": "decide_response.v2",
  "decision": {
    "answer": null,
    "alternatives": [],
    "recommendation": null,
    "confidence": null
  },
  "governance": {
    "fuji_decision": {},
    "policy_result": {},
    "enforcement": {
      "action": "DEFER",
      "defer_target": "<human-review queue reference>"
    },
    "risk": {}
  },
  "evidence": {
    "items": [],
    "retrieval": {},
    "citations": []
  },
  "audit": {
    "request_id": "...",
    "trace_id": "...",
    "trustlog_ref": "<non-null: defer event MUST be logged>",
    "replay_ref": null
  },
  "diagnostics": {
    "warnings": [],
    "degraded_modes": [],
    "tool_status": {}
  },
  "compat": {
    "v1_fields": {},
    "migration_notes": []
  }
}
```

> These enforcement paths are the canonical cases where `audit.trustlog_ref` MUST be non-null.
> The block/defer event is always logged to TrustLog regardless of whether a `decision.answer`
> is returned. v1 compatibility tests (Phase 2) must include at least one BLOCK scenario.

### Section intent (non-normative)

- `decision`: user-facing decision/result semantics.
- `governance`: FUJI/policy/enforcement/risk outputs needed for policy review and compliance.
- `evidence`: evidence items, retrieval context, and citation metadata.
- `audit`: stable identifiers for tracing and replay linkage.
  - `request_id`, `trace_id`: map from existing v1 fields.
  - `trustlog_ref`: stable identifier referencing the TrustLog entry for this decision;
    MUST be non-null for all FUJI enforcement events (BLOCK, DEFER).
  - `replay_ref`: **new field with no v1 equivalent**. Introduction scoped to Phase 3.
    Format TBD during Phase 0 inventory (candidate: opaque string token referencing the
    Continuation Runtime replay index). MUST NOT be populated in the Phase 1 shadow payload.
- `diagnostics`: operational signals for internal debugging/health visibility.
- `compat`: transitional envelope for v1-compatible consumers.
  - `v1_fields`: **field-mapping index** (not a data copy) of the form
    `{ "v1_field_name": "v2.section.field_path" }`, populated only when the response
    is served to a caller that has not opted into v2.
    Callers MUST NOT receive both the structured v2 sections and a full v1 copy simultaneously.
    The mapping index MUST NOT include fields excluded by Rule 5 (secrets, raw PII).
  - `migration_notes`: human-readable deprecation notices keyed by v1 field name.

## Compatibility and Safety Rules

1. **v1 remains default** until downstream migration is validated.
2. **No field removal in this planning PR**.
3. v2 introduction must be **additive first**, behind migration controls.
4. Governance/audit fields must remain **replay-safe** and deterministic enough for investigation workflows.
5. Diagnostics must not leak secrets or raw PII.
6. `trustlog_ref` and `replay_ref` should be stable identifiers, not raw internal blobs.
7. `compat.v1_fields` MUST be a mapping index, not a data copy. Full v1 payload
   mirroring is explicitly prohibited to prevent payload doubling.

## Phased Migration Plan

### Phase 0 — v1 Inventory and Classification

- Freeze and document current v1 field inventory.
- Classify each field into: `decision`, `governance`, `evidence`, `audit`, `diagnostics`, or `compat`.
- Mark ambiguous fields with owner and migration note.

### Phase 1 — Version Tag + Shadow v2 Payload

- Add `schema_version` support.
- Keep v1 as the default external contract.
- Introduce optional v2 shadow payload behind feature flag for internal comparison.

### Phase 2 — Parity and Regression Safety

- Add snapshot/serialization tests that compare v1 and v2 semantic parity where expected.
- Add negative tests for redaction and safe diagnostics behavior.

### Phase 3 — Internal Exposure and SDK Preparation

- Expose v2 in internal API surfaces and SDK preview pathways.
- Publish migration notes and mapping guidance from v1 fields to v2 sections.
- Define `replay_ref` format (opaque token vs. structured ref) and populate it in the
  SDK preview pathway alongside `trustlog_ref`.

### Phase 4 — Controlled Deprecation of Selected v1 Compat Fields

- Deprecate selected compatibility fields only after downstream consumers have an explicit migration path.
- Keep deprecation timelines and removals tied to usage telemetry and release governance.

## Future Implementation Acceptance Checklist

- [ ] Typed v2 schema exists.
- [ ] Serialization tests exist.
- [ ] Redaction/privacy tests exist.
- [ ] v1 compatibility tests exist.
- [ ] Documentation examples exist.
- [ ] API contract test exists.
- [ ] Migration feature flag exists.
- [ ] Telemetry/TrustLog/replay references are stable identifiers.

## Architectural Alignment

This plan is intentionally aligned with current boundary and safety principles:

- Responsibility boundaries remain unchanged across Planner / Kernel / FUJI / MemoryOS as defined in `docs/architecture/core_responsibility_boundaries.md`.
- Continuation enforcement remains conceptually separate from FUJI safety semantics; see `docs/architecture/continuation_enforcement_design_note.md` where relevant.
- TrustLog, FUJI, and pipeline concepts are preserved as existing systems of record and policy gating; this proposal only restructures response contract boundaries.

## Non-Goals (for this PR)

- No modification of runtime decision logic.
- No FUJI policy behavior change.
- No TrustLog storage/encryption behavior change.
- No immediate SDK breaking changes.

This document defines a migration strategy, not a shipping v2 implementation.
