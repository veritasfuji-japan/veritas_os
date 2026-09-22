# Observable Digest Resolver Security Review v1

## 1. Status

- **Phase:** pre-behavior adversarial security review.
- **Review revision:** 1.1 (16 primary controls + 7 cross-cutting paths + composite scenarios).
- **Resolver behavior:** not implemented or authorized.
- **Contract baseline:** `observable-digest-resolver-contract-v1`.
- **Activation status:** **BLOCKED**.

This review treats the resolver contract as a **hard invariant**, not as descriptive documentation.

The machine-readable threat matrix is:

`security/observable_digest_resolver_security_review_v1.json`

## 2. Governing question

The review is organized around one question:

> Can the resolver report what it observed without silently deciding what may be believed or done?

The answer must remain **yes under adversarial conditions** before behavior can be activated.

## 3. Hard invariant

Every future resolver result must preserve:

```text
Resolution Evidence
!= Boundary Validation
!= Admissibility
!= Authority
!= Execution Permission
```

and the contract-fixed non-amplification guarantees:

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

No security control, retry, cache, fallback, redirect, credential, or error handler may change those fields.

## 4. Review result

The review preserves **16 primary adversarial-control classes** and adds **7 cross-cutting adversarial paths** after external review.

The cross-cutting paths are not replacements for the primary controls. They test whether individually reasonable controls can interact to create an unauthorized conclusion.

The review therefore now covers:

```text
16 primary control classes
+ 7 cross-cutting adversarial paths
+ 10 composite adversarial scenarios
```

The crucial question is not only whether each control works in isolation, but whether any combination can manufacture a conclusion stronger than the evidence directly supports.

The review identifies **16 required primary adversarial-control classes**.

All are currently marked:

```text
REQUIRED_NOT_IMPLEMENTED
```

That status is intentional because resolver behavior does not yet exist.

Therefore the security review does **not** claim the resolver is secure or ready to activate.

It establishes the conditions that must be met before implementation may become behavioral.

## 5. Adversarial control classes

The review freezes the following threat classes:

1. scheme allowlist and SSRF;
2. redirects;
3. DNS changes / rebinding;
4. network egress;
5. credentials;
6. tenant / scope isolation;
7. retries;
8. fallbacks;
9. cached evidence;
10. stale results / time;
11. partial failures;
12. ambiguous errors;
13. timeouts / cancellation;
14. response / resource bounds;
15. transport trust / authenticity;
16. evidence_ref / logging.

Each class contains:

- the authority-amplification risk;
- required controls;
- required negative tests;
- explicit implementation status.

## 6. Redirect boundary

Redirects are a high-risk authority-amplification path.

Default posture:

```text
redirects = disabled
```

If a future reviewed resolver profile permits redirects:

- every hop must repeat scheme, hostname, resolved-IP, tenant, and egress validation;
- credentials must not be forwarded across an origin change;
- redirect count must be bounded;
- each hop must remain separately visible as evidence;
- a redirect cannot change resolver profile, trust root, credential scope, or authority semantics.

A public initial host redirecting to a private, loopback, link-local, metadata-service, or otherwise denied address must fail closed.

## 7. Retry boundary

A retry is a new observation attempt, not a repair of history.

Therefore:

```text
timeout -> retry -> success
```

must not become:

```text
success only
```

The earlier uncertainty must remain visible.

Retries are disabled by default unless a reviewed profile explicitly permits bounded retries.

No retry may:

- erase previous failure evidence;
- widen locator scope;
- change credentials;
- change trust root;
- alter execution permission;
- convert uncertainty into historical certainty.

## 8. Fallback boundary

No implicit fallback is permitted across:

- locator scheme;
- resolver profile;
- store;
- credential;
- trust root;
- network path;
- local path.

A primary failure cannot silently become success through an alternate path.

Any future fallback must be:

- explicit;
- reviewed;
- bounded;
- independently evidenced.

## 9. Cached evidence boundary

Cache presence is not current observation.

Cached material must preserve:

- original source provenance;
- original `observed_at`;
- cache age;
- expiry metadata where applicable.

A cache hit cannot assert:

- freshness;
- authenticity;
- digest match;
- current admissibility;
- Authority;
- execution permission.

A cache hit must not erase a prior unresolved state.

## 10. DNS and peer-address boundary

Hostname validation alone is insufficient.

Future network resolution must:

- validate every resolved address;
- reject private, loopback, link-local, multicast, reserved, unspecified, and metadata-service targets unless a separately reviewed deployment contract explicitly requires a bounded private resolver profile;
- validate IPv4 and IPv6 consistently;
- protect against encoded / alternate address forms;
- detect public-to-private rebinding;
- verify the connected peer address remains permitted.

Any reconnect or allowed redirect must repeat those checks.

## 11. Credential boundary

Resolver credentials must be:

- read-only;
- least privilege;
- resolver/store scoped;
- tenant scoped;
- distinct from execution credentials.

Resolver credential access must never create or restore execution Authority.

Secrets must never appear in:

- resolver result;
- `evidence_ref`;
- logs;
- exceptions;
- audit payloads.

Ambient credentials are not an allowed fallback.

## 12. Stale results and time

`RESOLVED` does not mean fresh.

The resolver reports `observed_at`; freshness remains a downstream validation responsibility.

Old, future-dated, malformed, or clock-ambiguous observations cannot be silently rewritten as current truth.

## 13. Partial failure boundary

Partial bytes are not a resolved digest.

Transport interruption, truncated responses, parsing failure, incomplete hashing, cancellation, or resource-limit exhaustion must remain:

```text
UNRESOLVED
```

unless complete contract-conformant resolution evidence exists.

## 14. Ambiguous error boundary

Free-text exception content has no contract authority.

Unknown operational exceptions cannot become `RESOLVED`.

Typed predicates remain the only failure-semantics input.

Ambiguous timeout, cancellation, transport, or parser outcomes remain unresolved.

## 15. Resource boundary

Future behavior must bound:

- response bytes;
- decompressed bytes;
- parsing depth;
- processing time;
- redirects;
- retries.

Resource exhaustion cannot trigger unsafe fallback.

## 16. Transport trust boundary

Authenticated transport is required for future network profiles.

Transport authenticity alone does not prove:

- digest match;
- freshness;
- policy admissibility;
- Authority;
- execution permission.

Trust-root selection must be explicit and evidence-visible.

## 17. evidence_ref boundary

`evidence_ref` is metadata.

It is not:

- an instruction to fetch;
- an authorization token;
- a trust anchor by itself;
- proof of authenticity;
- proof of freshness.

A malicious `evidence_ref` must not cause network, filesystem, or execution activity merely because it is present.

## 18. Cross-cutting adversarial paths

Before behavior implementation, the review also freezes seven cross-cutting paths.

### 18.1 Canonicalization and parser differentials

Different parsers, encodings, duplicate-key behavior, Unicode normalization, or serialization paths must not produce different resolver semantics from the same bounded input.

Security-critical bytes and structured forms must have one frozen canonical interpretation where hashing, comparison, signing, caching, or auditing depends on it.

Ambiguity must reduce what can be concluded.

It must never produce a parser-dependent `RESOLVED`.

### 18.2 Confused deputy and authority provenance

The resolver service may possess broader store access than a caller.

That broader service capability must not be exercised on behalf of a caller unless the exact tenant/scope/delegation is explicitly permitted and evidence-visible.

The resolver must preserve the provenance of:

- caller identity;
- resolver identity;
- tenant;
- locator namespace;
- credential class;
- allowed read scope.

This is **read-access authority provenance only**.

It is never VERITAS execution Authority.

### 18.3 Time-of-check / time-of-use

Security-critical properties can change after validation and before use.

Examples include:

- DNS answer;
- connected peer;
- credential validity;
- trust root;
- evidence object version;
- cached object identity.

The identity/version checked must remain bound to the material actually used.

If that continuity cannot be established, the result must remain blocked or unresolved.

### 18.4 Nondeterministic resolution

Ambient state, unordered inputs, race timing, random source selection, or multiple conflicting candidates must not silently determine what evidence is treated as authoritative.

For the same frozen request and pre-state, the resolver must either produce the same bounded interpretation or explicitly surface nondeterminism/conflict.

### 18.5 Resource-exhaustion amplification

Individually bounded mechanisms may still multiply into unbounded aggregate work.

Therefore a future resolver needs one global end-to-end budget across:

- wall time;
- bytes;
- decompressed bytes;
- DNS answers;
- redirects;
- retries;
- parser work;
- candidate count.

Local limits cannot multiply into a larger implicit budget.

Budget exhaustion remains unresolved and cannot trigger fallback or more work.

### 18.6 Supply-chain and trust-root substitution

Security review of one dependency/trust configuration must not silently transfer to a substituted parser, plugin, CA bundle, trust root, network adapter, or resolver dependency.

Security-critical dependencies and trust material must have explicit identity/version/integrity provenance.

Material changes reopen review.

### 18.7 Evidence integrity and audit ordering tampering

A later audit view must not become more certain because failed, ambiguous, repeated, or late attempts were deleted, reordered, duplicated, spliced, or selectively retained.

Where ordering is claimed, the system must preserve enough evidence to establish:

- attempt identity;
- request identity;
- observation time;
- evidence digest;
- predecessor/order relation.

If ordering evidence is missing or tampered with, certainty must decrease.

The system must not reconstruct a cleaner history.

## 19. Required proof obligations

Before resolver behavior can be authorized, the exact implementation must prove four things.

### What was observed

The result must bind to the exact:

- request;
- locator;
- resolver profile;
- resolver identity;
- evidence/digest bytes actually processed.

### When it was observed

The system must preserve enough timing and attempt-order evidence to distinguish:

- initial attempt;
- retry;
- cache observation;
- timeout;
- late completion;
- later re-resolution.

### Under which read-access authority

The system must preserve the bounded provenance of:

- caller identity;
- resolver identity;
- tenant/scope;
- credential class;
- trust configuration.

This must never be confused with execution Authority.

### What the resolver is forbidden to infer

The resolver remains forbidden to infer or manufacture:

- freshness;
- authenticity beyond the exact validated transport/evidence scope;
- digest match;
- boundary-validation success;
- admissibility;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation.

## 20. Composition rule

The security boundary must hold under combinations, not only isolated controls.

The frozen rule is:

```text
No combination of individually permitted mechanisms
may produce a conclusion stronger than
the evidence chain directly supports.
```

The matrix therefore freezes 10 composite adversarial scenarios combining redirects, DNS rebinding, credentials, retries, cache, parser differentials, TOCTOU, fallbacks, resource exhaustion, authority provenance, and audit tampering.

A composite scenario must not manufacture:

- freshness;
- authenticity;
- digest match;
- boundary validation;
- admissibility;
- Authority;
- execution permission.

A missing, conflicting, ambiguous, or tampered evidence chain must remain blocked, unresolved, conflict-visible, or not provable according to the exact case. It must not be repaired into a convenient success.

## 21. Activation gate

Resolver behavior remains **BLOCKED** until all of the following are true:

1. every threat-matrix control is implemented by a separate reviewed behavior change or an explicitly reviewed dependency;
2. required negative tests execute against the actual behavior path;
3. all negative tests pass on the exact implementation SHA;
4. non-amplification constants remain unchanged;
5. no implicit fallback or ambient credential path exists;
6. security evidence is re-run after final wiring;
7. the exact implementation is reviewed for new authority-amplification paths;
8. all seven cross-cutting adversarial paths are implemented or explicitly mitigated and tested;
9. composite adversarial scenarios pass against the exact behavior SHA;
10. the implementation can prove what was observed, when, under which bounded read-access authority, and which inferences remain forbidden.

## 22. Non-claims

This review does not establish:

- production security;
- resolver correctness;
- SSRF resistance in a runtime resolver;
- secure DNS handling in runtime;
- credential security in runtime;
- external penetration-test results;
- independent security validation;
- certification;
- customer production readiness.

It is a pre-behavior threat model and activation gate.

## 23. Next step after this review

The next step is **not** to activate the resolver.

The next bounded step is to review the expanded threat model, cross-cutting paths, proof obligations, and composite adversarial scenarios and decide whether the pre-behavior security boundary is complete.

Only after that review may a minimal behavior implementation be proposed, and that implementation must remain behind the activation gate until the exact behavior path passes the frozen security evidence.
