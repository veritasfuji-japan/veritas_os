# Decision Semantics (Phase-1 Contract)

This document is the **source-of-truth contract** for Phase-1 decision semantics.

## Runtime enforcement status

This contract is now **runtime-enforced** in:

- `veritas_os/core/pipeline/pipeline_response.py::_derive_business_fields`
- `veritas_os/api/schemas.py::DecideResponse`
- `veritas_os/core/decision_semantics.py`

Spec and runtime are aligned: gate canonicalization, stop-reason ordering, and
forbidden gate/business/human-review combinations are validated before response
finalization.

## Legacy / alias values

`gate_decision` now prefers canonical public output.
Legacy values are accepted on ingestion/compatibility paths and normalized before
response finalization.

## Tightening status (implemented in runtime)

- Canonical public values are prioritized: `proceed|hold|block|human_review_required`.
- Legacy values (`allow|deny|modify|rejected|abstain`) are normalized before validation.
- Forbidden combination checks are enforced on canonicalized values.
- `unknown` remains fallback-compatible, but normal runtime derivation converges to canonical values.
- Mission Control adapters now canonicalize legacy gate aliases before UI rendering.

## A. gate_decision semantics table

| value | current meaning | primary intent | UI label expectation | legacy / alias | recommended | relation / notes | priority level |
|---|---|---|---|---|---|---|---|
| `proceed` | Safe to continue execution path | Execute with normal monitoring | Proceed | No | Yes | Canonical positive gate | Lowest stop priority |
| `hold` | Do not execute yet; gather evidence/policy readiness | Pause and remediate | Hold | No | Yes | Canonical pause state | Medium |
| `block` | Fail-closed stop, execution denied | Prevent execution | Blocked | No | Yes | Canonical deny state | Highest |
| `human_review_required` | Escalate to human adjudication boundary | Human handoff | Human review required | No | Yes | Canonical escalation state | High |
| `allow` | Legacy synonym for non-blocked FUJI status | Compatibility with older payloads | “response generation allowed (not case approval)” | Yes | Limited | Usually normalized to `proceed` unless other stop reasons override | Low |
| `deny` | Legacy deny-like signal | Compatibility | Blocked by gate | Yes | Limited | Normalized to `block` in derivation | High |
| `modify` | Legacy “allowed with modification” | Compatibility | Gate hold | Yes | Limited | Often mapped into `hold` path | Medium |
| `rejected` | Legacy deny alias | Compatibility | Blocked by gate | Yes | Limited | Treated same as `block` | High |
| `abstain` | Legacy deferred/abstain signal | Compatibility | Gate hold | Yes | Limited | Treated as `hold` in public semantics | Medium |
| `unknown` | Fallback when decision is absent | Defensive default | Gate status | Yes | No (except fallback) | Eventually resolved through stop reasons and defaults | Lowest |

### Clarifications

- `allow` and `proceed` are **not equivalent labels** at API semantics level. `allow` is legacy status input; `proceed` is canonical public gate output.
- `block`, `deny`, and `rejected` are treated as deny-family, with `block` as canonical output.
- `human_review_required` is a canonical **gate decision** value in current API output, while `human_review_required` boolean remains a parallel flag.

## B. business_decision semantics

| value | meaning | when used | gate coupling |
|---|---|---|---|
| `APPROVE` | Case can proceed in business lifecycle | No stop reasons and no evidence/policy gaps | Usually with `proceed` |
| `DENY` | Case denied | Hard fail-closed stop | `block` |
| `HOLD` | Case paused for non-terminal governance reasons | Rule/control/audit readiness incomplete | Usually `hold` |
| `REVIEW_REQUIRED` | Human adjudication required | Ambiguity/boundary/human flag requires review | `human_review_required` |
| `POLICY_DEFINITION_REQUIRED` | Policy boundary/rule definition missing | Explicit policy-definition reason present | Often `hold` |
| `EVIDENCE_REQUIRED` | Required evidence is incomplete | `missing_evidence` non-empty | Typically `hold` |

## C. gate_decision × business_decision combination rules

| combination | status |
|---|---|
| `gate=block` + `business=APPROVE` | Forbidden |
| `gate=hold` + `business=APPROVE` | Forbidden |
| `gate=human_review_required` + `human_review_required=false` | Forbidden |
| `gate=proceed` + `business=DENY` | Forbidden |
| `gate=proceed` + `business=APPROVE` | Allowed |
| `gate=hold` + `business=HOLD` | Allowed |
| `gate=hold` + `business=EVIDENCE_REQUIRED` | Allowed |
| `gate=human_review_required` + `business=REVIEW_REQUIRED` | Allowed |
| legacy gate values with canonical business values | Input-tolerated, runtime-normalized to canonical |

Additional runtime invariants:

- `gate=proceed` + `human_review_required=true` is forbidden.
- `business=REVIEW_REQUIRED` + `human_review_required=false` is forbidden.
- `business=APPROVE` + `human_review_required=true` is forbidden.

## D. stop_reasons priority (current implementation order)

Current order in `_derive_business_fields`:

1. `rollback_not_supported` → `block`
2. `irreversible_action` + `audit_trail_incomplete` → `block`
3. `secure_prod_controls_missing` → `block`
4. deny-family input (`deny/rejected/block`) → `block`
5. `required_evidence_missing` → `hold`
6. `high_risk_ambiguity` (with `risk_score >= 0.8`) → `human_review_required`
7. `approval_boundary_unknown` OR `human_review_required=true` → `human_review_required`
8. Any of `rule_undefined` / `audit_trail_incomplete` / `secure_controls_missing` OR legacy hold-family input (`hold/modify/abstain`) → `hold`
9. else → `proceed`

## E. `human_review_required` positioning

- Boolean flag meaning: operator/human adjudication is required before execution.
- Relationship to gate: if true (or boundary ambiguity exists), gate is elevated to `human_review_required`.
- Relationship to business decision: typically maps to `REVIEW_REQUIRED`.
- UI guidance: show gate value first, then show flag as explicit reviewer obligation.

## F. relationship with `decision_status`

- `decision_status` remains for backward compatibility with older FUJI-facing payloads.
- `gate_decision` / `business_decision` are public semantics for case governance.
- Legacy clients may still emit/consume `decision_status` (`allow|modify|rejected|block|abstain`).
