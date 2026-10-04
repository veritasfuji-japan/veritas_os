# Observable Digest Resolver Activation Evidence Review v1

Review revision: **1.1**

## 1. Status

```text
ACTIVATION_EVIDENCE_REVIEW_OPEN

activation_authorized = false
activation_approved = false
activation_performed = false
effect_path_connection_authorized = false
```

This review exists to answer one narrow question:

> What evidence would be required to justify activating the already-implemented resolver behavior?

It does **not** authorize activation.

It does **not** approve activation.

It does **not** connect the resolver to `/v1/decide`, Bind, execution permission, or any effect-bearing path.

The machine-readable companion is:

`security/observable_digest_resolver_activation_evidence_review_v1.json`

## 2. Baseline

Merged implementation:

`f3db837d8233afbb998195890525fcbe511c2f2c`

Validated final PR head:

`0fe3e95364fe9c7abdd3e58e5ec3f861935123ff`

Observed PR-head result:

```text
23 / 23 workflows success
```

The merge commit is file-identical to the validated PR head.

Frozen implementation identities:

```text
resolver module blob:
64431fecf69579d8554cbc590a67ce8ca9d4a612

behavior-test blob:
a247bf768ca7a0ac6f65ac13fbb2e07664336b30

implementation-manifest blob:
6f17cb0bb2027efda7516e71050feb23d9828283
```

No separate exact-merge-SHA CI rerun has been observed.

That distinction remains explicit.

## 3. Mark implementation-review outcome

The external implementation review concluded that no described semantic or security issue required correction before proceeding to the next evidence / activation-review stage.

That result is recorded only as:

```text
IMPLEMENTATION_REVIEW_ONLY
```

It is not:

- authorization;
- activation approval;
- permission to wire a runtime caller;
- permission to connect an effect-bearing path;
- certification;
- independent security audit.

## 4. Governing separation

The activation review preserves:

```text
Implementation Correctness
!= Authorization
!= Admissibility
!= Approval
!= Execution Permission
!= Activation
```

and:

```text
RESOLVED
!= Policy ALLOW
!= Authority
!= Human Approval
!= Bind Authorization
!= Execution Permission
```

No artifact in this review is allowed to self-authorize activation.

## 5. Current runtime reachability

At the frozen implementation baseline, repository search shows the resolver callable only in:

- its own implementation module;
- focused resolver behavior tests.

No production runtime caller is currently declared.

This review adds an executable source-level isolation regression so that production code cannot silently import or call the resolver without changing this gate.

This is a source-level proof only.

It is not a production deployment or runtime-packaging proof.

## 6. Proposed activation target boundary

The only future activation class contemplated by this review is:

```text
RESOLVER_EVIDENCE_ONLY_ACTIVATION_V1
```

If separately authorized later, it may only make the existing:

```text
separate_store_readonly_v1
```

resolver callable from **one explicitly named evidence-only consumer**.

The activation target is intentionally not named yet.

Therefore activation is not currently justified.

The future consumer may use resolver output only as evidence.

It may not directly transform `RESOLVED` into:

- policy ALLOW;
- admissibility;
- Authority;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation;
- external effect.

## 7. Gate AER-01 — Exact implementation identity

Current status:

```text
CLOSED / PASS
```

Rule of One:

```text
AER-01_EXACT_IMPLEMENTATION_IDENTITY_V1
```

AER-01 is closed only for the exact implementation identity evidenced below.

### Exact merged-main proof target

```text
94faafa1a42fde18a3cf03c41e54e731266e82fb
```

Dedicated workflow:

`Observable Digest Resolver AER-01 Exact Identity V1`

Exact-main push run:

`37208356216`

Job:

`111454223084`

Artifact:

`11305563535`

Artifact name:

`observable-digest-resolver-aer01-v1-94faafa1a42fde18a3cf03c41e54e731266e82fb`

Artifact ZIP SHA-256, independently recomputed after download:

`8103465d432ef2470a887dacca70c5a76d88561ba18c5c9b090735c89ed8f989`

The GitHub artifact metadata reported the same SHA-256 digest.

### Frozen identities verified by the proof report

```text
resolver runtime blob:
64431fecf69579d8554cbc590a67ce8ca9d4a612

focused behavior-test blob:
a247bf768ca7a0ac6f65ac13fbb2e07664336b30

implementation-manifest blob:
5174dab99f9284498966a4bd8968db5ec910b052
```

All expected and observed identities matched.

The downloaded `proof-report.json` recorded:

- `result = PASS`;
- `tested_sha = 94faafa1a42fde18a3cf03c41e54e731266e82fb`;
- `github_sha_env = 94faafa1a42fde18a3cf03c41e54e731266e82fb`;
- all identity matches true;
- all frozen activation-safety invariants true.

The downloaded focused test log recorded:

```text
49 passed in 0.43s
```

### Closure determination

AER-01 is therefore:

```text
CLOSED / PASS
```

for this exact identity only.

This closure does not authorize activation, approve activation, perform activation, or authorize effect-path connection.

It does not close AER-02 through AER-11.

Any material implementation-identity change invalidates this exact AER-01 pin and requires a new evidence round.

## 8. Gate AER-02 — Runtime reachability inventory

Current status:

```text
PENDING_CI_PROOF
```

The resolver must remain unreachable from undeclared production callers.

Before activation:

- every production import/call path must be explicit;
- the exact future consumer must be declared;
- a source-level regression must reject any additional undeclared caller.

Activation wiring itself is a material security change.

## 9. Gate AER-03 — Named activation target and caller

Current status:

```text
NOT_DEFINED
```

Activation cannot be justified until one exact caller is identified.

The activation record must bind:

- exact caller module / component;
- caller identity provenance;
- `caller_id_hash` provenance;
- exact resolver profile;
- exact namespace scope;
- exact activation configuration;
- default-disabled state.

“No caller has been chosen yet” is a valid reason to remain blocked.

## 10. Gate AER-04 — Snapshot provenance and admissibility

Current status:

```text
NOT_PROVEN
```

The resolver currently proves only:

> exact membership of a contract-conformant digest record in the supplied immutable snapshot under the bounded profile.

Activation requires a separate answer to:

- who or what creates the snapshot;
- where its source evidence comes from;
- how source-to-snapshot provenance is preserved;
- why the snapshot is admissible for the intended consumer;
- what freshness rule applies if the consumer requires freshness.

The resolver may not self-assert those properties.

## 11. Gate AER-05 — Consumer non-amplification

Current status:

```text
NOT_PROVEN
```

A future consumer must prove that:

```text
RESOLVED
→ evidence available
```

never silently becomes:

```text
RESOLVED
→ ALLOW / Authority / Approval / Bind / Execution
```

The existing hard-false semantic guarantees constrain the resolver itself.

Activation additionally requires proof that the **consumer** does not amplify them.

## 12. Gate AER-06 — Failure and uncertainty propagation

Current status:

```text
NOT_PROVEN
```

The resolver itself already fails closed.

Activation requires proof that the consumer also preserves:

```text
UNRESOLVED
failure
missing provenance
contradiction
mutation
uncertainty
    ↓
same or weaker conclusion only
```

No fallback, convenience normalization, stale cache, alternate identity, or permissive default may convert degraded resolver evidence into a stronger downstream conclusion.

## 13. Gate AER-07 — Explicit authorization and approval

Current status:

```text
NOT_GRANTED
```

This review cannot satisfy this gate itself.

A later, separate record must explicitly authorize and approve:

- exact implementation identity;
- exact target;
- exact caller;
- exact profile;
- exact namespace scope;
- exact activation configuration;
- explicit non-effect-bearing boundary.

Authorization must not be inferred from:

- implementation success;
- tests passing;
- external design review;
- merge status;
- repository presence.

## 14. Gate AER-08 — Effect-path separation

Current status:

```text
CURRENTLY_PROHIBITED_NOT_YET_ACTIVATION_PROVEN
```

The implementation is currently unwired from:

- `/v1/decide`;
- Bind authorization;
- execution permission;
- effect-bearing dispatch.

Any future activation wiring must prove that this remains true.

A resolver result must never become a bypass around downstream governance boundaries.

This activation gate can never authorize an effect-path connection.

That would require a separate architecture/security review.

## 15. Gate AER-09 — Default-disabled activation, deactivation, rollback

Current status:

```text
NOT_DEFINED
```

A future activation mechanism must be:

- default disabled;
- explicit;
- scope-bound;
- reversible;
- fail closed on configuration ambiguity.

Deactivation or rollback must not create new authority, fallback, or stale activation.

Any material change reopens this review.

## 16. Gate AER-10 — Post-activation evidence

Current status:

```text
NOT_AVAILABLE
```

If activation is ever separately approved, the next proof must bind:

- exact activated code identity;
- exact configuration identity;
- exact declared caller;
- exact profile and namespace;
- runtime proof that semantic guarantees remain hard false;
- runtime proof that no effect-bearing connection was introduced.

Activation is not considered closed merely because an enable switch was changed.

## 17. Gate AER-11 — Independent challenge and auditability

Current status:

```text
NOT_DEFINED
```

The initial ten-gate foundation has been externally reviewed for completeness and was assessed as capturing the essential activation boundaries.

One additional activation-specific dimension is now frozen:

```text
Independent Challenge / Auditability
```

This gate asks:

> Who, separate from the implementation author and activation requester, is responsible for challenging the activation evidence, which exact artifacts must they inspect, and how is their approval or refusal preserved so the decision remains independently examinable?

AER-11 does **not** replace AER-07.

```text
Explicit Authorization / Approval
!= Independent Challenge / Auditability
```

Authorization cannot substitute for independent review.

Independent review cannot manufacture authorization.

### Reviewer separation

The independent reviewer must be explicitly identified and must be separate from:

- the implementation author;
- the activation requester.

The authorization approver does not automatically count as the independent reviewer.

Any role overlap or conflict must be explicitly disclosed and reviewed rather than silently accepted.

### Minimum review package

The reviewer must inspect a frozen artifact manifest that includes at least:

- exact implementation identity and code/test artifact identities;
- AER-01 through AER-09 evidence and current status;
- exact proposed activation target;
- exact proposed caller;
- exact resolver profile;
- exact namespace;
- exact activation configuration;
- snapshot provenance / admissibility evidence;
- consumer non-amplification evidence;
- failure / uncertainty propagation evidence;
- the separate AER-07 authorization / approval record;
- effect-path separation evidence;
- default-disabled enable / disable / rollback evidence;
- all open findings, limitations and non-claims.

The package must make adverse or incomplete evidence visible.

It must not present only successful evidence.

### Challenge semantics

The independent review must permit:

- challenge;
- refusal;
- abstention;
- unresolved findings.

It must not be structured as an approval-only path.

The frozen decision vocabulary is:

```text
APPROVE
REFUSE
ABSTAIN
```

Rules:

- missing reviewer decision blocks activation;
- `REFUSE` blocks activation;
- `ABSTAIN` blocks activation;
- unresolved blocking findings block activation;
- `APPROVE` does not create execution Authority;
- `APPROVE` does not authorize an effect-path connection.

### Auditability

The preserved review record must bind:

- reviewer identity and role;
- reviewer-separation / conflict disclosure;
- review timestamp;
- exact implementation identity reviewed;
- exact activation configuration reviewed;
- reviewed-artifact manifest identity;
- decision;
- unresolved findings, if any;
- explicit limitations and non-claims.

The review record and artifact manifest must be durably preserved and independently reconstructable.

If the review record is missing, stale, contradictory, or cannot be verified against the frozen package, activation remains blocked.

### Closure condition

AER-11 closes only when an identified independent reviewer:

1. is demonstrably separate from the implementation author and activation requester;
2. inspects the frozen activation evidence package;
3. records an independently verifiable `APPROVE` decision;
4. has no unresolved blocking finding;
5. has the decision and reviewed-artifact manifest durably preserved and reconstructable.

This gate remains distinct from both authorization and post-activation evidence.

## 18. Current activation decision

Current result:

```text
ACTIVATION NOT JUSTIFIED
```

This is not a failure of the resolver.

It is the expected result because key activation-specific evidence does not exist yet.

Current blockers include:

- exact activation target not defined;
- consumer semantics not proven;
- snapshot admissibility not defined;
- explicit authorization not granted;
- explicit approval not granted;
- activation / deactivation mechanism not defined;
- post-activation evidence cannot exist before activation;
- no separate exact-merge-SHA focused rerun observed.

## 19. Closure rule

Activation review may close only when:

1. AER-01 through AER-09 and AER-11 are closed;
2. a separate explicit authorization/approval record exists;
3. independent review remains separate from authorization and is durably auditable;
4. exact activation wiring remains evidence-only and non-effect-bearing;
5. no material change has reopened the security review.

AER-10 closes only after any separately approved activation.

AER-11 must close before activation.

The activation-review document itself can never authorize activation.

## 20. Non-claims

This review does not establish:

- authorization;
- activation approval;
- activated runtime behavior;
- production deployment;
- production snapshot provenance;
- customer deployment;
- independent security audit;
- penetration-test completion;
- certification;
- permission to connect an effect-bearing path.

Its purpose is to make the missing activation evidence explicit before any activation decision is considered, including the independent challenge and auditability required to make that decision externally examinable.
