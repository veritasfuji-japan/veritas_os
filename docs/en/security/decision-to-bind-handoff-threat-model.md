# Decision-to-Bind handoff threat model

## Boundary and assets

This threat model applies to the future `CanonicalDecisionHandoff` specified in
the [architecture contract](../architecture/canonical-decision-to-bind-handoff-v1.md).
It protects action/target integrity, actor authority, approvals, decision and
policy lineage, state freshness, and the separation between formation and Bind.
The artifact and test vectors are specification-only and create no authority or
external effect.

## Threats and required fail-closed controls

| Threat | Example | Required control |
|---|---|---|
| Semantic laundering | `ALLOW` is accepted as authority, `APPROVE` as Human Approval, or authenticated identity as execution authority | Ignore non-authoritative sources when satisfying security requirements; separately validate requirement, evidence, and binding. Mere source-signal presence is not itself invalid. |
| Action inference | `next_action` becomes executable | Require typed canonical action from explicit structured input. |
| Confused deputy | Authenticated caller requests an out-of-scope effect | Verify exact actor/action/target/policy-scope authority. |
| Identity/authority conflation | API identity is treated as authorization | Bind independent Authority Evidence. |
| Stale Authority Evidence | Expired role is reused | Verify issuer, validity window, freshness, and hash/ref. |
| Stale Human Approval | Expired receipt is reused | Bind operation and enforce validity/expiry. |
| Target substitution | Candidate for A is changed to B | Hash canonical target and reject mutation/mismatch. |
| Action substitution | Approval for A is reused for B | Bind receipt to exact canonical action and parameters. |
| TOCTOU/state drift | Formation state differs at Bind | Keep formation fingerprint distinct from Bind live observation. |
| Policy drift | Policy B supersedes decision policy A | Verify semantic digest, effective time, expiry, and supersession. |
| Cross-request lineage substitution | Request A TrustLog is attached to B | Require identical request and source identities plus chain verification. |
| Candidate mutation after hashing | Target/action changes post-validation | Deterministically hash the full canonical candidate and compare. |
| Replay artifact substitution | Unrelated replay is attached | Independently verify replay identity, request, decision, and hash. |
| Hash-domain ambiguity | Different payloads share an informal hash label | Version canonical serialization and domain-separated included fields. |
| Fail-open missing values | Empty/`None` defaults appear valid | Treat missing mandatory values as incomplete/invalid, never allow. |
| Structural refusal laundering | Refused lineage is repackaged | Preserve transformation-stable refusal; require reconstruction. |
| Approval replay | Receipt authorizes another amount/user/target | Enforce exact scope, nonce/reference, time, and one-operation semantics. |
| Authority replay | Credential is reused beyond scope/window | Bind evidence to operation and verify current validity. |
| Reviewer/runtime mismatch | Offline reviewer fixture is called live evidence | Label synthetic provenance and verify runtime artifact identities. |
| Decision-proof/Bind-proof false linkage | The independently verified #2098 Decision proof and #2097 Bind proof are presented as sharing canonical Decision → ExecutionIntent → Bind lineage merely because #2099 packages and verifies both. | Refuse connected-lineage claims absent shared canonical lineage evidence. |

## Security posture and residual risk

Missing, ambiguous, stale, mismatched, or unverified values never default to
allow. `REVIEW_REQUIRED` is a stop, not permission. Structural refusal occurs
before Bind and cannot be healed by attaching evidence. Bind remains a separate
adjudication boundary and must revalidate live state and time-sensitive
evidence.

Semantic laundering occurs when a non-authoritative signal is accepted as
satisfying a security requirement. The defensive behavior is to ignore or
reject that source for that purpose. Its mere presence in a source decision
does not prove that an inference was attempted and does not automatically make
the whole handoff `INVALID`: the independently required field remains missing
and receives its normal fail-closed status.

**Security warning:** this document defines controls but implements none. Until
a separately reviewed future implementation establishes canonical decision
lineage and live evidence validation, any claimed Decision-to-Bind connection
is untrusted. #2097 proves the separate external Bind boundary, #2098 proves the
Decision pipeline through `DecideResponse` and STOP, and #2099 independently
verifies and packages both proofs. None creates the lineage connection.
