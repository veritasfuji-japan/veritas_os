# Canonical Decision Artifact v1

## Status, purpose, and boundary

This specification defines the immutable
`CanonicalDecisionArtifact` representation of one finalized, normalized
VERITAS decision event. It supplies a stable `decision_id`, `decision_hash`,
and `decision_ts` for the decision side. The current `/v1/decide` response has
`request_id`, but does **not** emit any of those three authoritative canonical
values. A production standalone builder and integrity verifier now implement
the v1 contract as a pure, independently testable runtime primitive. They are
not yet wired to `/v1/decide`, pipeline finalization, persistence, TrustLog,
replay, `CanonicalDecisionHandoff`, `ExecutionIntent`, or Bind.

The processing boundary is exactly:

```text
normalized pre-Bind DecideResponse snapshot
  -> canonical decision projection
  -> versioned, domain-separated canonical serialization
  -> decision_hash -> decision_id -> CanonicalDecisionArtifact -> STOP
```

The artifact is not a `DecisionCandidate`, `CanonicalDecisionHandoff`,
`ExecutionIntent`, Authority Evidence, Human Approval, `BindReceipt`, execution
instruction, or permission. In particular:

* `request_id != decision_id`; a request identifier is not decision identity.
* response hash != decision hash.
* HTTP arrival time, TrustLog retrieval time, CI time, and current wall clock
  != the canonical historical `decision_ts`.
* `ALLOW != authority`; `APPROVE != Human Approval Receipt`.
* authenticated identity != execution authority.
* `chosen != canonical executable action`; `next_action != intended_action`.
* `READY_FOR_GUARDED_PROMOTION != execution`.

These separations are security boundaries. Human approval is required before a
future runtime implementation may change governance or Bind behavior.

## Source and finalization contract

The source contract is `DecideResponse` after its ordinary Pydantic validation
and normalization, identified independently by
`canonical-decision-projection/v1`. Raw provider output, a raw request, HTTP
response bytes, normalized `DecideResponse`, and the canonical projection are
five different values. Only the declared projection of the normalized response
is hashed; `SHA256(response.json())` is prohibited.

`decision_ts` is captured at the future decision-finalization boundary: the
instant the normalized pre-Bind decision state becomes final. It MUST be passed
to the future producer at that boundary and MUST NOT be inferred or backfilled.
V1 requires exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`: UTC `Z`, exactly six
fractional digits, and no offset or naive representation in the emitted
artifact. A future boundary may normalize an aware offset input to UTC before
artifact construction; naive and invalid inputs are refused.

The producer MUST consume a pre-Bind snapshot. It MUST refuse production if
any post-Bind field has a JSON value other than `null`. The complete v1 set is
`bind_outcome`, `bind_failure_reason`, `bind_reason_code`, `bind_receipt_id`,
`execution_intent_id`, `bound_execution_intent_id`,
`authority_check_result`, `constraint_check_result`, `drift_check_result`,
`risk_check_result`, `bind_summary`, `bind_operator_summary`, and
`bind_operator_detail`. It MUST NOT silently strip those values to reconstruct
a decision post hoc. `BLOCKED` and `ROLLED_BACK` results are still post-Bind.
Later Bind augmentation cannot alter an already emitted artifact.

## Exact artifact and projection

The closed JSON Schema is
[`schemas/canonical-decision-artifact-v1.schema.json`](../../../schemas/canonical-decision-artifact-v1.schema.json).
The top-level fields are exactly `format_version`, `hash_profile`,
`decision_id`, `decision_hash`, `decision_ts`, `request_id`, `source_contract`,
and `decision`. `source_contract` is exactly `{type: "DecideResponse",
projection_version: "canonical-decision-projection/v1"}`.

The `decision` projection includes exactly:

1. `formation_status`: exposes incomplete formation rather than inventing
   missing governance identity;
2. `chosen_binding`: binds the selected normalized value without granting it
   action semantics;
3. `decision_status` and `rejection_reason`: bind the overall disposition;
4. `gate_decision` and `business_decision`: bind the distinct safety and
   business conclusions without laundering either into authority;
5. `next_action`, `actionability_status`, and
   `requires_bind_before_execution`: bind recorded decision-side guidance and
   its execution boundary without forming an action;
6. `human_review_required`: binds the recorded requirement signal, not proof
   that review occurred or that approval is unnecessary;
7. `required_evidence`, `missing_evidence`, and `satisfied_evidence`: bind the
   ordered, normalized recorded evidence state, not evidence authenticity;
8. `rationale`, `refusal_reason`, `actionability_block_reason`, and
   `actionability_refusal_type`: bind decision/refusal meaning relevant to an
   audit; and
9. `governance_identity_binding`, `lineage_promotability_binding`, and
   `transition_refusal_binding`: bind the exact normalized objects, when
   present, without widening their schemas or repairing structural refusal.

All keys are mandatory; genuine absence is represented by the schema-defined
`null`, never omission. `COMPLETE` means only that the normalized source has a
governance identity object and `governance_identity_binding` is non-null.
`INCOMPLETE` means it is unavailable and that binding is null. Neither value
asserts independent cryptographic verification. The schema rejects both
contradictory combinations. No policy snapshot, lineage, signer, or authority
is fabricated. Governance identity alone does not satisfy the handoff's full
`policy_lineage`. A non-promotable/refused source remains bound as such and is
never repaired by artifact construction.

### Closed decision semantics

The v1 vocabularies mirror normalized `DecideResponse`: `decision_status` is
`allow`, `modify`, `rejected`, `block`, or `abstain`; `gate_decision` is
`proceed`, `hold`, `block`, or `human_review_required`; `business_decision` is
`APPROVE`, `DENY`, `HOLD`, `REVIEW_REQUIRED`,
`POLICY_DEFINITION_REQUIRED`, or `EVIDENCE_REQUIRED`; and
`actionability_status` is `reviewable_only`,
`bind_required_before_execution`, `blocked`, `human_review_required`, or
`formation_transition_refused`. This is deliberately the strict pre-Bind
subset of the wider `DecideResponse` vocabulary. Runtime
`actionable_after_bind` requires a committed Bind outcome plus both Bind receipt
and execution-intent lineage, so the pre-Bind CDA producer refuses rather than
represents that state. Compatibility
aliases (`allow`, `deny`, `modify`, `rejected`, `abstain`) are never artifact
gate values. Although `unknown` remains a compatibility/default input to the
current response model, v1 refuses canonical production from that unresolved
gate state rather than representing it.

Schema semantic conditions mirror the source contract: `proceed` and
`APPROVE` each require `human_review_required=false`; `REVIEW_REQUIRED` and
`human_review_required` gate are bidirectionally coupled and require the
boolean to be true; and `(block, APPROVE)`, `(hold, APPROVE)`, and
`(proceed, DENY)` are forbidden. A future verifier MUST run schema validation,
including these conditions, before hash verification. The existing
`DecideResponse` remains the source of truth; this specification does not
create a divergent runtime semantics system.

The two bound actionability fields also preserve the pre-Bind execution
boundary. `reviewable_only`, `bind_required_before_execution`, and
`human_review_required` require `requires_bind_before_execution=true`;
`blocked` and `formation_transition_refused` require it to be false. An
`actionability_status` of `human_review_required` requires the review boolean
to be true, but the reverse is intentionally not global because a more
restrictive status may retain that signal. The stable structural-refusal
runtime additionally requires `formation_transition_refused` to retain
`human_review_required=true`.

### Opaque-value bindings

Because current `chosen`, `governance_identity`, `lineage_promotability`, and
`transition_refusal` sources are extensible objects, v1 places each behind a
closed digest boundary. For a binding, canonical-serialize the exact normalized
JSON-safe value using the rules below, then hash the UTF-8 bytes of this object:

```json
{"profile":"<binding profile>","value":<normalized value>}
```

The profiles are, respectively:

* `veritas.canonical-decision.chosen-value/v1`;
* `veritas.canonical-decision.governance-identity/v1`;
* `veritas.canonical-decision.lineage-promotability/v1`; and
* `veritas.canonical-decision.transition-refusal/v1`.

The binding records that profile and the lowercase SHA-256 digest. Chosen
digest != candidate hash != executable action authorization. Governance and
formation digests bind exact recorded values; they do not attest their truth.

## Hash profile, serialization, and preimage

`hash_profile` is fixed to `veritas.canonical-decision/v1`; the algorithm is
SHA-256. The exact preimage is the following object, using values copied from
the artifact:

```json
{
  "profile": "veritas.canonical-decision/v1",
  "format_version": "canonical-decision-artifact/v1",
  "request_id": "<artifact.request_id>",
  "decision_ts": "<artifact.decision_ts>",
  "source_contract": "<artifact.source_contract object>",
  "decision": "<artifact.decision object>"
}
```

Thus the preimage fields are **exactly** `profile`, `format_version`,
`request_id`, `decision_ts`, `source_contract.type`,
`source_contract.projection_version`, and every `decision` field enumerated in
the preceding section. There is no “all except” rule. `hash_profile` declares
the same procedure but the preimage domain key is named `profile`.
`decision_hash`, `decision_id`, and every value derived from either are
excluded, proving that the construction is non-circular.

Canonical JSON here deliberately matches the repository's current
`canonical_json_dumps`: UTF-8 JSON, Unicode preserved, lexicographically sorted
map keys, compact separators `,` and `:`, JSON `null`/`true`/`false`, list order
preserved, and no insignificant whitespace. Inputs MUST contain only JSON
types; finite JSON numbers only; NaN and Infinity are refused. Python repr,
sets, tuples, object identity, filesystem data, UUID generation, current time,
environment variables, Git SHA, and CI identifiers are forbidden. The test
reference additionally uses `allow_nan=False`; this tightens input rejection
without changing bytes for the JSON-safe values accepted by the repository
helper. No generic helper is changed by this specification.

`decision_hash` is the 64-character lowercase SHA-256 hex digest of those
bytes. The content-addressed identifier uses the full digest:

```text
decision_id = "cda:v1:sha256:" + decision_hash
```

Consequently, the same preimage always has the same hash and ID; any included
field change produces a new decision event, hash, and ID. `request_id` alone
cannot determine the ID. Once emitted, an artifact is immutable. A reconsidered
decision is a new event; a future, separate contract may link supersession.

## Explicit exclusions

The following normalized response values do not define v1 identity:

* `ok`, `error`, `version`, response latency/`meta`, temporary paths, UI or
  reviewer summaries, `persona`, `memory_citations`, `memory_used_count`,
  `plan`, `planner`, `reason`, `critique`, `debate`, `values`, `evidence`,
  `telos_score`, `fuji`, `rsi_note`, `extras`, `gate`, `evo`, disclosure and
  notification presentation, diagnostics, and coercion metadata: volatile,
  debug, compatibility, presentation, or separately governed context;
* `alternatives` and mirrored `options`: unselected compatibility surfaces
  whose generated/default alternative IDs are not stable decision identity;
  only the selected value is bound once;
* `query`, `pipeline_steps`, `trust_log`, `user_summary`, and
  `deterministic_replay`: request/audit/replay material independently verified
  later, not canonical decision state;
* participation, pre-Bind detection/preservation details, recovery guidance,
  WAT diagnostics, and other additive extension fields: diagnostic or
  separately versioned contexts not selected for the minimal v1 projection;
* every Bind field listed in the source-boundary section: post-decision state
  that must never retroactively redefine the decision; and
* `decision_hash`, `decision_id`, artifact verification status, TrustLog chain
  state, replay proof, candidate, Authority Evidence, Human Approval,
  `ExecutionIntent`, `BindReceipt`, adapter, and external-effect state: derived
  identity or independent security domains.

Changing an excluded response field does not change canonical identity;
changing an included value does. There is no undocumented source-field
fallback.

Vectors marked `EMIT` are producer-eligible normalized source fixtures.
`HASH_REFERENCE_ONLY` vectors intentionally isolate hash sensitivity and make
no claim that the isolated tuple is reachable through coupled runtime
semantics. `REFUSE` vectors document producer refusal. The golden and excluded
field stability vectors are `EMIT`; mutation vectors are hash-reference-only.

## Verification and independent domains

The standalone verifier fails closed: (1) validate schema/version; (2) exclude
the two identity outputs; (3) construct the exact v1 preimage; (4) canonicalize;
(5) SHA-256; (6) compare `decision_hash`; (7) derive the expected full
`decision_id`; (8) compare it; and (9) reject any mismatch. The artifact has no
`verified: true` shortcut.

Canonical decision hash, chosen-value digest, candidate hash, handoff
assertion-value digest, TrustLog chain hash, replay artifact hash, Authority
Evidence hash, Human Approval receipt hash, and Bind intent hash are separate
domains. No digest substitutes for another. TrustLog and replay remain
independently verified properties matched later to request/decision identity;
neither is in this preimage, avoiding circularity.

A verified artifact may later map `artifact.request_id` to
`source_decision.request_id`, `artifact.decision_id` to
`source_decision.canonical_decision_id`, `artifact.decision_hash` to
`source_decision.canonical_decision_hash`, and `artifact.decision_ts` to
`source_decision.canonical_decision_ts`. Copying strings is insufficient:
handoff provenance must record artifact reference/hash, verification mechanism,
and successful independent status. The artifact does not create the handoff or
candidate. It never derives actor, target system/resource, or canonical action
from chosen, next action, rationale, business result, or API identity. Authority
Requirement, Authority Evidence, Human Approval/not-required proof, full policy
lineage, and expected state remain independent.

## Threat model

V1 fails or prevents: request ID substituted for decision ID; HTTP-response
hash substitution; current-time timestamp backfill; post-Bind reconstruction;
chosen/action laundering; ALLOW/APPROVE authority laundering; compatibility or
volatile-field hash drift; alternate serialization; self-hash recursion;
cross-domain digest confusion; cross-request substitution; reuse of one ID with
modified state; governance substitution; and erasure of structural refusal.
The verifier proves internal structure and content integrity only. A party able
to replace an entire artifact and recompute its hash and ID can produce an
internally self-consistent artifact; trusted origin and provenance remain a
separate future layer.

## Non-claims and remaining work

This milestone provides no live `/v1/decide` emission, canonical candidate
extraction, Authority Evidence, Human Approval verification, live policy
verification, TrustLog verification, replay
verification, `CanonicalDecisionHandoff` creation, guarded promotion,
`ExecutionIntent`, Bind, external effect, or production/customer/regulatory
certification. A later PR must define and review the finalization capture,
pre-Bind producer, artifact persistence/reference, independent verification,
TrustLog/replay matching, structured candidate/evidence inputs, and handoff
consumer. It must not change the existing handoff validator implicitly.
