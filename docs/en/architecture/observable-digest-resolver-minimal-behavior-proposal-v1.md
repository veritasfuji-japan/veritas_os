# Observable Digest Resolver Minimal Behavior Proposal v1

## 1. Status

- **Proposal only.**
- **Resolver behavior implemented:** no.
- **Resolver behavior authorized:** no.
- **Activation gate:** **BLOCKED**.
- **Contract baseline:** `observable-digest-resolver-contract-v1`.
- **Security-review baseline:** v1.1.
- **Product main baseline:** `88f56546ffc9cfa03b26c20deddd2cae7d676448`.

This document proposes the smallest behavior worth implementing next.

It does **not** activate a resolver, wire `/v1/decide`, access a network, fetch credentials, perform policy decisions, or change execution permission.

The machine-readable companion is:

`security/observable_digest_resolver_minimal_behavior_proposal_v1.json`

## 2. Governing principle

The proposal preserves the frozen boundary:

```text
Resolution Evidence
!= Boundary Validation
!= Admissibility
!= Authority
!= Execution Permission
```

It also adds the security-review monotonicity rule as a behavior requirement:

```text
uncertainty
contradiction
delay
mutation
loss of provenance
    ↓
may reduce what the system can conclude
but must never increase it
```

The resolver must fail closed whenever the evidence chain can no longer justify the requested resolution conclusion.

## 3. Why the first behavior should be non-network

The security review is mature enough to freeze, but the first behavior does not need to exercise every future transport path at once.

The narrowest useful first profile is a deterministic, non-network, read-only `separate_store://` resolver over an immutable injected snapshot.

This deliberately excludes:

- HTTP / HTTPS;
- DNS;
- redirects;
- retries;
- fallback;
- cache;
- filesystem reads;
- database reads;
- object-store SDKs;
- environment lookup;
- ambient credentials;
- trust-root selection.

Those paths remain outside the initial profile rather than being partially implemented.

Adding any of them later reopens the relevant security review before activation.

## 4. Proposed initial profile

Profile:

```text
separate_store_readonly_v1
```

Purpose:

> Resolve one exact canonical `separate_store://` locator against one immutable typed snapshot supplied to the resolver.

Supported locator form:

```text
separate_store://<namespace>/<object-key>
```

Examples:

```text
separate_store://digests/wat-5
separate_store://wat_observables/event-0001
```

A configuration prefix such as:

```text
separate_store://wat_observables
```

may continue to exist as metadata, but the minimal resolver behavior requires a full object locator.

## 5. Locator grammar

The initial profile is intentionally conservative.

A supported locator must satisfy all of the following:

- scheme is exactly `separate_store`;
- ASCII only;
- no percent encoding;
- no query;
- no fragment;
- no userinfo;
- no empty segments;
- no `.` or `..` segments;
- maximum locator length: 500 characters;
- namespace matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`;
- every object-key segment matches the same pattern;
- one to eight object-key segments.

Noncanonical input is rejected.

The resolver does not normalize ambiguous input into a more convenient locator.

## 6. Data-source boundary

The first implementation, if separately approved, receives one **immutable typed snapshot** from its caller or test harness.

The resolver itself performs no:

- network access;
- filesystem access;
- database access;
- object-store access;
- environment lookup;
- credential lookup;
- shared mutable-state access.

Lookup is exact-key only.

This is intended to make the first behavior useful for contract and security proof without silently introducing transport authority.

## 7. Access model

The profile carries an explicit bounded read scope.

The minimum profile configuration includes:

- `resolver_id`;
- exact allowed namespace;
- explicit allowed `caller_id_hash` set.

The initial profile has no service credential, execution credential, delegation, impersonation, or ambient identity.

Therefore:

```text
profile-pinned read access
!= execution Authority
```

A caller outside the allowlist, or a locator outside the pinned namespace, fails before snapshot lookup.

## 8. Proposed store record

The immutable snapshot maps one canonical locator to one immutable typed record:

```text
resolved_digest
record_version
```

Requirements:

- `resolved_digest` is exactly `sha256:<64 lowercase hex chars>`;
- `record_version` is exactly `1`;
- no additional fields.

The first profile does not parse an arbitrary external payload.

A malformed typed record produces `SCHEMA_MISMATCH`.

## 9. Resolution behavior

For a valid request:

1. verify the requested resolver profile;
2. validate locator grammar without permissive normalization;
3. verify caller allowlist membership;
4. verify namespace scope;
5. perform one exact immutable snapshot lookup;
6. validate the typed store record;
7. return the existing resolver-contract result.

The profile has:

```text
redirects = 0
retries = 0
network requests = 0
cache lookups = 0
fallbacks = 0
credential lookups = 0
```

## 10. Result semantics

A successful exact lookup may return:

```text
RESOLVED
```

with the stored SHA-256 digest.

That means only:

> the exact canonical locator was found in the exact immutable snapshot under the active bounded profile, and the typed record contained a contract-conformant SHA-256 digest.

It does not mean:

- digest match;
- freshness;
- external authenticity;
- policy admissibility;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation.

All six existing non-amplification guarantees remain hard `false`.

## 11. Failure mapping

The proposed first profile uses only existing resolver-scoped predicates:

- `LOCATOR_MISSING` — no usable locator;
- `LOCATOR_MALFORMED` — unsupported scheme or invalid/noncanonical grammar;
- `AUTHZ_DENIED` — caller or namespace outside the frozen read scope;
- `RESOLUTION_FAILED` — exact canonical locator absent from the snapshot;
- `SCHEMA_MISMATCH` — typed store record violates the frozen record shape.

`UNKNOWN_TRANSIENT` is not emitted by the initial pure snapshot profile because it has no transport or mutable external dependency.

Free-text exception content remains non-semantic.

## 12. Time model

The behavior proposal uses an explicit injected UTC clock.

The resolver must not hide an ambient wall-clock read inside otherwise deterministic behavior.

Tests may inject a fixed timestamp.

Determinism is defined over:

```text
request
+ resolver profile
+ immutable snapshot
+ injected observed_at
```

The same frozen inputs must produce the same bounded result and internal observation.

## 13. Internal observation object

The proposal includes one immutable internal observation object for proof and future audit integration.

It is **not** a new public authority surface and does not change the existing resolver contract.

Proposed fields include:

- request ID and request hash;
- locator;
- resolver profile;
- resolver ID;
- caller ID hash;
- access scope;
- profile hash;
- snapshot hash;
- observed timestamp;
- lookup outcome;
- resolved digest or null;
- typed failure predicates;
- existing semantic guarantees.

For this first profile:

```text
public result evidence_ref = null
persistence = false
audit emission = false
```

Durable audit integration remains a later, separately reviewed step.

## 14. Four proof obligations

### What was observed

The resolver must bind the result to the exact:

- request;
- canonical locator;
- profile;
- immutable snapshot identity;
- typed record / digest outcome.

### When it was observed

The resolver preserves the injected `observed_at` exactly.

### Under which bounded read-access authority

The resolver preserves:

- caller ID hash;
- resolver ID;
- profile-pinned namespace scope.

No ambient or execution credential participates.

### What the resolver is forbidden to infer

The resolver remains forbidden to infer:

- freshness;
- authenticity beyond exact typed snapshot membership;
- digest match;
- boundary-validation success;
- admissibility;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation.

## 15. Composition and monotonicity rule

The initial profile must preserve both rules:

```text
No combination of individually permitted mechanisms
may produce a conclusion stronger than
the evidence chain directly supports.
```

and:

```text
evidence degradation
must never increase conclusion authority
```

Examples:

- missing provenance cannot turn an unresolved lookup into resolved;
- a malformed record cannot be repaired by fallback;
- a denied caller cannot reach lookup through another identity;
- a noncanonical locator cannot be normalized into success;
- snapshot ambiguity cannot select a convenient digest.

## 16. Required tests for a later behavior PR

A separate implementation PR must prove at least:

- valid exact locator returns `RESOLVED` with the exact stored digest;
- all non-amplification guarantees remain false;
- missing locator -> `LOCATOR_MISSING`;
- unsupported or noncanonical locator -> `LOCATOR_MALFORMED`;
- percent encoding / query / fragment / dot segments / empty segments / Unicode / overlength forms are rejected;
- disallowed caller -> `AUTHZ_DENIED` before lookup;
- cross-namespace locator -> `AUTHZ_DENIED` before lookup;
- missing key -> `RESOLUTION_FAILED`;
- invalid typed record -> `SCHEMA_MISMATCH`;
- same frozen inputs produce byte-equivalent bounded results;
- snapshot construction order does not change the outcome;
- snapshot mutation is unavailable through the resolver interface;
- no network / DNS / redirect / retry / cache / filesystem / database / environment / credential path is reachable;
- loss of provenance or evidence quality can only preserve or reduce conclusion strength.

Applicable v1.1 security-review negative and composite tests must also execute against the exact behavior SHA.

## 17. Explicit non-scope

The minimal profile does not add:

- HTTP / HTTPS;
- DNS;
- redirect handling;
- network egress;
- filesystem or database resolution;
- object-store SDK access;
- credential providers;
- ambient credentials;
- retries;
- fallback;
- cache;
- trust-root selection;
- signature verification;
- freshness validation;
- expected-digest comparison;
- policy or admissibility decisions;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation;
- durable audit persistence;
- TrustLog integration;
- `/v1/decide` wiring;
- default operator UI.

## 18. Activation gate

This proposal does not authorize behavior.

Behavior remains blocked until:

1. this proposal is reviewed;
2. behavior is implemented in a separate PR;
3. the implementation stays within this exact profile boundary, or security review is reopened;
4. the frozen behavior tests pass on the exact implementation SHA;
5. applicable security-review v1.1 negative and composite tests pass on the exact implementation SHA;
6. no network, credential, retry, redirect, cache, persistence, mutable shared-state, or alternate-scheme path has been added implicitly;
7. `/v1/decide` and execution paths remain unwired until a later explicit activation decision.

## 19. Non-claims

This proposal does not establish:

- a working resolver;
- runtime security;
- production readiness;
- external-store interoperability;
- network security;
- customer deployment;
- independent security validation;
- certification.

It freezes the smallest implementation boundary that may be considered next.
