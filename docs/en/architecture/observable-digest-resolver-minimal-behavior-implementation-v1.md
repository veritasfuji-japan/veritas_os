# Observable Digest Resolver Minimal Behavior Implementation v1

## Status

```text
IMPLEMENTED_NOT_AUTHORIZED_NOT_ACTIVATED
behavior_implemented = true
behavior_authorized = false
behavior_activated = false
activation_gate = BLOCKED
```

This record describes the isolated implementation candidate for:

`separate_store_readonly_v1`

Implementation:

`veritas_os/audit/observable_digest_resolver.py`

Behavior proof:

`veritas_os/tests/test_observable_digest_resolver_behavior.py`

The implementation is not wired to `/v1/decide`, Bind, execution permission, effect-bearing dispatch, or any external store/network path.

## Exact initial behavior

The implementation accepts one contract-valid request, one frozen resolver profile, one immutable caller-supplied snapshot, and one explicit UTC observation timestamp.

It performs:

```text
request/profile validation
-> strict locator grammar validation
-> caller allowlist check
-> exact namespace-scope check
-> one exact immutable-snapshot lookup
-> strict typed-record validation
-> RESOLVED or UNRESOLVED result
```

It performs no external I/O.

## Supported locator

Only:

```text
separate_store://<namespace>/<object-key>
```

is accepted.

The implementation rejects rather than normalizes:

- unsupported scheme;
- leading/trailing whitespace;
- percent encoding;
- query;
- fragment;
- userinfo;
- empty path segments;
- dot segments;
- Unicode locator content;
- overlength locator;
- noncanonical snapshot locator keys.

## LOCATOR_MISSING clarification

The frozen resolver exchange schema requires `request.locator` and `result.locator` to be non-empty strings.

Therefore a genuinely absent/empty locator cannot be represented as a contract-valid runtime request/result pair.

For this profile:

```text
LOCATOR_MISSING = upstream locator-selection predicate
```

A missing or empty locator is rejected before a contract-valid `ObservableDigestResolverRequest` is constructed.

The resolver runtime itself can emit:

- `LOCATOR_MALFORMED`;
- `AUTHZ_DENIED`;
- `RESOLUTION_FAILED`;
- `SCHEMA_MISMATCH`.

`UNKNOWN_TRANSIENT` is not emitted by this pure snapshot profile.

## Read-access authority

The profile contains:

- exact resolver ID;
- exact namespace;
- explicit allowed caller-ID hashes.

There is no service credential, execution credential, delegation, impersonation, ambient credential, or credential-provider lookup.

Caller authorization and namespace scope are checked before any snapshot provenance or lookup is exposed by the resolver. Pre-snapshot failures keep `snapshot_hash = null`.

Read-access authorization remains separate from VERITAS execution Authority.

## Immutable snapshot

The caller supplies a bounded immutable snapshot.

Snapshot construction:

- copies caller-provided mappings into frozen record envelopes;
- sorts entries deterministically;
- rejects duplicate or noncanonical locator keys;
- bounds entry and record-field counts;
- derives a deterministic snapshot hash.

Mutation of the caller's original mapping after snapshot construction cannot change the resolver's snapshot.

## Time and determinism

`observed_at` is explicitly injected and must be UTC ending in `Z`.

No hidden wall-clock lookup occurs in the resolver.

Determinism is defined over:

```text
request
+ profile
+ immutable snapshot
+ observed_at
```

The same frozen inputs produce the same bounded result and internal observation.

## Internal observation

The implementation produces an immutable internal observation binding:

- request ID and request hash;
- exact locator;
- resolver profile and resolver ID;
- caller ID hash;
- bounded access scope;
- profile hash;
- snapshot hash only after caller + namespace authorization reaches the snapshot boundary; pre-snapshot failures keep it null;
- observed timestamp;
- lookup outcome;
- resolved digest or null;
- typed failure predicates;
- hard-false semantic guarantees.

The observation is not persisted or emitted by this implementation.

## Semantic guarantees

Every result keeps these values false:

```json
{
  "authority_created": false,
  "execution_permission_changed": false,
  "digest_match_asserted": false,
  "boundary_validation_asserted": false,
  "uncertainty_erased": false,
  "remediation_executed": false
}
```

A `RESOLVED` result establishes only exact membership of a contract-conformant digest record in the supplied immutable snapshot under the bounded profile.

It does not establish freshness, external authenticity, digest match, admissibility, Human Approval, Bind authorization, execution permission, or remediation.

## Monotonic evidence rule

The implementation preserves:

```text
uncertainty
contradiction
mutation
loss of provenance
    ↓
may reduce what can be concluded
but must never strengthen it
```

Malformed locator, unauthorized caller, out-of-scope namespace, absent record, or invalid record shape all fail closed to `UNRESOLVED` rather than falling back, normalizing, retrying, or selecting a stronger conclusion.

## Explicitly unreachable in this profile

There is no:

- HTTP / HTTPS;
- DNS;
- redirect;
- retry;
- fallback;
- cache;
- filesystem read;
- database read;
- object-store SDK;
- environment lookup;
- credential provider;
- ambient credential;
- trust-root selection;
- persistence;
- audit emission;
- policy/admissibility decision;
- Human Approval;
- Bind authorization;
- execution permission;
- `/v1/decide` wiring;
- effect-bearing execution wiring.

## Activation boundary

Implementation is not activation.

This implementation remains blocked from activation until exact-SHA evidence closes the applicable behavior/security tests and a separate explicit activation decision is made.

Any addition of network, credentials, retries, redirects, cache, persistence, mutable shared state, another locator scheme, or execution wiring reopens the relevant security review.


## Activation evidence review

The implementation has passed external implementation review for the described boundary, but that does not authorize activation.

The independent activation-evidence gate is now defined at:

`docs/en/security/observable-digest-resolver-activation-evidence-review-v1.md`

with machine-readable companion:

`security/observable_digest_resolver_activation_evidence_review_v1.json`

Current activation-review posture:

```text
ACTIVATION_EVIDENCE_REVIEW_OPEN
activation_authorized = false
activation_approved = false
activation_performed = false
effect_path_connection_authorized = false
```

The gate intentionally records unresolved activation-specific evidence rather than treating implementation correctness as sufficient.
