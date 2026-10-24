# Bind-Boundary Governance Artifacts

## Implemented scope

VERITAS includes two **native governance artifacts** as first-class contracts:

1. `ExecutionIntent`
2. `BindReceipt`

`FinalOutcome` models bind-time terminal status.
Bind-boundary artifacts append to the existing TrustLog path so auditors can
traverse native lineage:

`decision artifact -> execution intent -> bind receipt`

## Why these artifacts exist

VERITAS already treats the decision artifact as the primary governance record.
This extension keeps that architecture intact and adds bind-boundary lineage:

- `ExecutionIntent` links an execution attempt directly to a `decision_id` and
  governance lineage (`policy_snapshot_id`, `actor_identity`, `decision_hash`).
- `BindReceipt` records bind-time checks (authority/constraint/drift/risk/
  admissibility), links back to both decision and execution intent, and carries
  TrustLog chain linkage (`trustlog_hash`, `prev_bind_hash`).
- `BindReceipt` also stores minimal replay/revalidation metadata:
  `bind_receipt_hash`, `execution_intent_hash`, copied governance identity,
  and a compact `revalidation_context` used for admissibility replay.

This provides explicit governance-native artifacts at the decision → bind
boundary without creating a parallel subsystem.

## Current boundary and caveats

Implemented in this repository:

- bind-time admissibility adjudication inputs on bind receipts
- bind terminal outcomes (`COMMITTED`, `BLOCKED`, `ESCALATED`, `ROLLED_BACK`)
- TrustLog lineage pointers and bind receipt list/export/detail endpoints
- shared compact `bind_summary` vocabulary across bind-governed mutation/export responses
- Mission Control bind-phase rendering on decision results

Not guaranteed by this document alone:

- tenant-specific external side-effect adapter coverage
- environment-specific production hardening and operational controls
- universal production-readiness claims across every deployment context

## Authenticated actor for governance mutations

`PUT /v1/governance/policy` and `POST /v1/governance/policy-bundles/promote`
use the API-authenticated principal from request state for `actor_identity` in
ExecutionIntent and BindReceipt. Caller-supplied `updated_by` and `X-Role`
labels do not establish that identity. Missing authenticated principal context
returns HTTP 403 before mutation. Existing role/tenant and approval checks still
apply, and the policy's `updated_by` remains caller-supplied display metadata.

This identifies an API credential, not an independently authenticated human.
It does not cryptographically authenticate the two approval records, establish
enterprise IAM integration, or change actor handling on other API routes.

## Compliance configuration policy source

`PUT /v1/compliance/config` reads the current governance policy through
`get_policy()` before Bind adjudication. Its `bind_adjudication` controls and
`updated_at` / `version` identity accompany the execution intent. The separate
runtime compliance configuration remains the state captured by the adapter for
drift checks and mutation; it is not the source of governance policy controls.

When policy requires TTL or approval freshness, missing evidence blocks or
escalates the update according to `missing_signal_default`, with HTTP 403 and no
configuration mutation. The current configuration request does not carry those
expiry signals, so enabling either requirement prevents updates through this
route until an appropriate evidence path is provided. Default policies without
these requirements retain the existing successful update behavior.

The focused HTTP tests use real route authentication, adapter and Bind
adjudication with isolated configuration and audit storage. They establish this
management-route policy boundary, not external-operation or customer-deployment
coverage.

## Policy promotion approval metadata

`POST /v1/governance/policy-bundles/promote` rejects the reserved
`bind_adjudication` key in client-supplied `approval_context` with HTTP 400
(`approval_context_policy_override_forbidden`) before invoking promotion.
Bind policy controls come from the current server governance policy.

The internal Bind engine accepts policy overrides from trusted callers. Passing
HTTP approval metadata directly to that mechanism previously let a promotion
request disable TTL or approval-freshness requirements. The regression tests
exercise the real HTTP route, helper, adapter and Bind evaluation using temporary
bundle files and an active pointer, with audit storage isolated. A control
request remains BLOCKED/ESCALATED under the configured missing-evidence policy;
an override request is rejected without changing the pointer. These fixtures do
not establish cryptographic bundle authenticity or production deployment safety.

## Governance update lineage boundary

`PUT /v1/governance/policy` rejects HTTP `policy_lineage` containing the reserved
`bind_adjudication` key with HTTP 400, before approval processing or mutation.
The current server-side governance policy supplies Bind controls; request
lineage cannot disable its TTL or approval-freshness requirements. Ordinary
lineage metadata and trusted internal helper overrides remain compatible.

Regression tests exercise the real HTTP, approval, adapter and persistence path
with a temporary governance policy. Control requests with missing required
signals remain BLOCKED/ESCALATED, and override requests produce no policy update
calls or file changes. This is a bounded API regression, not proof of all
execution paths or production IAM enforcement.

## Policy bundle verification before promotion

Signature-required promotion reuses `load_runtime_bundle()` during Bind
constraint validation, immediately before writing the active pointer, and in
postcondition verification. Invalid bundles are refused before the pointer is
written; a later verification failure retains the existing rollback path.

Verification requires manifest integrity and exact manifest-declared content
bindings, including canonical-IR digest, semantic hash, policy id and version.
Secure/prod posture or `VERITAS_POLICY_REQUIRE_ED25519=true` requires an Ed25519
signature with the trusted public key configured by `VERITAS_POLICY_VERIFY_KEY`.
Non-strict legacy SHA-256 mode verifies integrity only; it does not establish
signer authenticity. Bundles without content declarations must be rebuilt before
signature-required promotion. The trusted internal `require_signature=False`
compatibility option is not exposed by the public promotion request.

HTTP tests use generated Ed25519 keys, compiler-produced temporary bundles and
the real promotion/Bind path. Invalid signatures, modified manifests/bodies,
wrong/missing keys and missing signatures cause zero pointer writes. Controlled
changes after validation or after writing exercise revalidation and rollback.
This does not make the bundle directory immutable against concurrent filesystem
modification; filesystem ownership and subsequent runtime verification remain
separate boundaries.

## TrustLog and lineage integration

- `ExecutionIntent` appends as `kind=governance.execution_intent` via the
  existing `append_trust_log` implementation (same hash-chain/signing path).
- `BindReceipt` appends as `kind=governance.bind_receipt` via the same TrustLog
  append pipeline and receives the TrustLog chain hash in `trustlog_hash`.
- `prev_bind_hash` chaining is derived from prior bind receipts already stored
  in TrustLog (`bind_receipt_hash`), not from a new logging plane.
- Retrieval helpers resolve bind receipts by `bind_receipt_id`,
  `execution_intent_id`, or `decision_id` directly from TrustLog entries.
- Internal helper `veritas_os.policy.bind_revalidation.revalidate_bind_receipt`
  can re-run admissibility from receipt-contained context and verify lineage/hash
  linkage against an optional execution intent payload.

This keeps decision artifacts primary while extending native VERITAS governance
lineage toward bind-boundary control.

## Participation vs commitment admissibility

Bind artifacts govern **admissibility of commitment** at the bind boundary.
The additive pre-bind `participation_signal` family governs
**admissibility of participation** during decision formation.

The two layers are intentionally separate and composable:

- participation layer (upstream): governability signals before commit
- bind layer (boundary): commitment adjudication before real-world effect

Current upstream participation detection now includes an additive pre-bind
structural state classifier (`informative|participatory|decision_shaping`) on
`/v1/decide` via optional `pre_bind_detection_summary/detail` fields. This
remains non-binding and does not alter bind-time fail-closed adjudication.

An adjacent additive preservation layer now exposes
`pre_bind_preservation_summary/detail` (`open|degrading|collapsed`) to indicate
whether meaningful intervention remains viable at observation time. This is not
a bind outcome and not a rename of pre-bind detection.


## Companion summary vocabulary (`bind_summary`)

`BindReceipt` remains the full bind artifact contract.

`bind_summary` is the companion compact summary family: it is intentionally
smaller than the full receipt payload and is reused across mutation/export
responses so operators can triage bind outcomes without losing a path to the
full artifact (`/v1/governance/bind-receipts*`).

This keeps full-artifact and summary-object semantics explicit rather than
merging them into a single overloaded shape.

Canonical vocabulary used across backend schema, OpenAPI, and frontend surfaces:

- `bind_summary`: compact, shared operator-facing bind envelope.
- `bind_receipt` / `bind_receipt_id`: full artifact and stable lineage pointer.
- `execution_intent_id`: lineage pointer linking decision → execution intent → bind receipt.
- target metadata fields (`target_path_type`, `target_label`, `operator_surface`, `relevant_ui_href`):
  backend-owned canonical metadata for operator rendering.
- bind outcome/reason fields (`bind_outcome`, `bind_reason_code`, `bind_failure_reason`):
  compact triage vocabulary; full diagnostics remain in `BindReceipt` check payloads.

Legacy flat bind fields remain intentionally additive for compatibility.

## Runtime behavior impact

Additive to existing decision flows. Decision-phase semantics remain primary;
bind-phase semantics add an explicit boundary between approval and commitment.

## Operator interpretation in Mission Control

Mission Control keeps the decision artifact as the primary record and now shows
bind-phase as a lower-layer execution-governance outcome:

- Decision approved + `bind_outcome=COMMITTED`: approved and applied.
- Decision approved + `bind_outcome=BLOCKED`: approved but bind checks blocked.
- Decision approved + `bind_outcome=ESCALATED`: approved but requires escalation.
- Decision approved + `bind_outcome=ROLLED_BACK`: approved, attempted, then rolled back.

This distinction prevents operators from misreading decision-phase approval as
bind-phase commitment.

Mission Control Bind Cockpit also provides an additive **pre-bind governance
surface** in the receipt drill-down when optional payload fields are present:

- `pre_bind_detection_summary.participation_state`
- `pre_bind_detection_summary.concise_rationale`
- `pre_bind_detection_summary.primary_contributing_signals`
- `pre_bind_preservation_summary.preservation_state`
- `pre_bind_preservation_summary.intervention_viability`
- `pre_bind_preservation_summary.concise_rationale`
- `pre_bind_preservation_summary.main_contributing_conditions`

The UI renders these as an ordered pre-bind flow (`participation` →
`preservation` → `bind gate`) and keeps them visually separate from
`bind_outcome`/`bind_reason_code` to avoid vocabulary mixing.

## Minimal API example

`GET /v1/governance/decisions/export?limit=1`

```json
{
  "ok": true,
  "items": [
    {
      "decision_id": "dec-9001",
      "decision_status": "allow",
      "bind_outcome": "BLOCKED",
      "bind_receipt_id": "br-9001",
      "execution_intent_id": "ei-9001",
      "bind_failure_reason": "Constraint mismatch",
      "bind_reason_code": "CONSTRAINT_MISMATCH"
    }
  ]
}
```

`GET /v1/governance/bind-receipts/br-9001` returns the linked bind receipt
artifact with authority/constraint/drift/risk check payloads.

- VERITAS now keeps a tested bind coverage registry for API effect paths. Effect-bearing routes must be classified as `bind_governed` or documented as explicit `audited_exemption` entries (reason/risk/owner/review cadence), reducing the risk of TrustLog(recorded) being misread as execution permission without bind lineage.
