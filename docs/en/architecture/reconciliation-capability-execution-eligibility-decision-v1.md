# Reconciliation Capability Execution Eligibility Decision v1

Status: **DECIDED / IMPLEMENTED BY POLICY-GATED PROFILE V1**

## 1. Decision

VERITAS will treat authoritative downstream reconciliation capability as an execution-target eligibility precondition **only when the governing action/deployment policy requires authoritative reconciliation for that external effect**.

This is not a universal requirement for every target.

The decision is:

> **If policy requires authoritative reconciliation, a target must present current, independently anchored reconciliation-capability evidence before the external effect may proceed.**

The following capability classes may satisfy that prerequisite:

- `AUTHORITATIVE_QUERY`
- `AUTHORITATIVE_EVIDENCE`

The following classes do not satisfy it:

- `HEURISTIC_ONLY`
- `UNAVAILABLE_OR_UNVERIFIED`

This document fixes the intended future execution contract. It does not wire the requirement into the runtime yet.

## 2. Why this decision exists

VERITAS already treats ambiguous dispatch outcomes as `EFFECT_UNKNOWN` and prohibits blind redispatch.

That model can only close safely when the downstream system, or another accepted authoritative evidence source, can later answer what happened to the exact attempt.

Without such a capability, VERITAS can preserve uncertainty, but it cannot manufacture external truth.

Therefore reconciliation capability is not only a post-effect concern. For policy-selected external effects, it is part of deciding whether the target is suitable for automated execution at all.

## 3. Policy scope

The future enforcement must be policy-selected rather than globally hard-coded.

A policy may require authoritative reconciliation for effects such as:

- high-impact or high-risk external actions;
- actions whose duplicate execution could create material harm;
- actions that are difficult or impossible to reverse;
- actions for which an unresolved `EFFECT_UNKNOWN` state would create unacceptable operational risk; or
- any action explicitly designated by deployment policy as requiring authoritative reconciliation.

This document does not introduce a new risk taxonomy and does not redefine existing action classes.

The policy source must be deployment-controlled. A request or AI output must not be able to downgrade the requirement.

## 4. Satisfying the prerequisite

When authoritative reconciliation is required, evidence is admissible only if all of the following hold:

1. the capability class is `AUTHORITATIVE_QUERY` or `AUTHORITATIVE_EVIDENCE`;
2. the evidence passes the existing structural semantics for that class;
3. endpoint identity still matches the assessed endpoint;
4. target configuration still matches the assessed configuration;
5. the evidence is not expired or from the future;
6. the verifier identity/policy binding matches independently supplied trust anchors;
7. any expected evidence digest matches the presented artifact; and
8. the evidence remains non-authorizing by itself.

The machine-readable evidence and negative-proof validator added before this decision are evidence inputs to the future gate. They are not permission objects.

## 5. Non-satisfying capability

If policy requires authoritative reconciliation:

- `HEURISTIC_ONLY` must fail the eligibility prerequisite;
- `UNAVAILABLE_OR_UNVERIFIED` must fail the eligibility prerequisite;
- missing evidence must fail the prerequisite;
- stale evidence must fail the prerequisite;
- target-binding drift must fail the prerequisite; and
- caller-declared verifier identity must not replace deployment-controlled trust anchors.

Heuristic signals may assist investigation, but they must not be promoted into authoritative reconciliation capability.

## 6. Enforcement placement

The intended future enforcement point is **before authorization consumption and before transport may begin**.

The future sequence should preserve the existing separation:

```text
ExecutionIntent
-> policy determines whether authoritative reconciliation is required
-> current reconciliation-capability evidence is verified
-> current target/configuration/verifier bindings are rechecked
-> if required capability is absent or invalid: fail closed
-> native authorization consumption
-> durable attempt ownership
-> transport
-> EFFECT_UNKNOWN when outcome is ambiguous
-> independent reconciliation
-> retrospective receipt/outcome
```

The capability check must not itself consume the authorization.

A failed capability check therefore must not create a consumed authorization, a network attempt, retry permission, or a terminal effect claim.

## 7. Binding and drift

Future enforcement should bind the accepted capability state strongly enough that a different target or materially changed target configuration cannot inherit a prior approval implicitly.

At minimum, the enforcing design should bind or recheck:

- reconciliation-capability evidence digest;
- endpoint identity binding digest;
- target configuration digest;
- required capability class/policy requirement;
- verifier identity and verifier policy identity/hash; and
- assessment freshness.

If any required binding changes before effect, execution must fail closed and require a newly admissible capability assessment under the current policy.

This document does not require a live network probe of the reconciliation endpoint immediately before dispatch. Structural capability and current trust binding are distinct from transient service availability.

## 8. Temporary outage versus absent capability

A target can possess authoritative reconciliation capability even when its read path is temporarily unavailable.

Therefore:

- temporary lookup outage after dispatch does not retroactively make the original target ineligible;
- the effect remains `EFFECT_UNKNOWN`;
- automatic redispatch remains prohibited; and
- reconciliation may resume when the authoritative path becomes available again.

By contrast, a target that never had an accepted authoritative reconciliation path cannot satisfy a policy that requires one.

## 9. Capability loss after dispatch

If an attempt has already been dispatched and the authoritative reconciliation surface later disappears, becomes unavailable, or loses trust:

- do not convert the state to `CONFIRMED_NO_EFFECT`;
- do not infer success from heuristics;
- do not infer failure from absence;
- do not enable automatic retry;
- preserve `EFFECT_UNKNOWN`; and
- escalate to another authoritative evidence path or governed human investigation.

Human involvement may coordinate evidence collection. A human assertion alone is not external-effect proof unless the governing reconciliation contract explicitly accepts and verifies that evidence form.

## 10. Relationship to the frozen controlled proof

The existing frozen controlled Decision-to-Effect proof remains unchanged.

It already demonstrates a controlled target with:

- caller-controlled pre-dispatch correlation identity;
- durable downstream persistence;
- independent read-only lookup;
- `EFFECT_UNKNOWN` preservation during lookup outage; and
- no blind redispatch.

This decision does not rewrite that proof.

A later enforcing PR must explicitly state whether it extends the frozen contract, creates a new proof version, or adds a policy-gated execution profile. It must not silently widen the old claim.

## 11. Required proof before runtime enforcement

Before this decision is wired into execution, focused proof must cover at least:

1. policy requires authoritative reconciliation + current `AUTHORITATIVE_QUERY` -> prerequisite passes;
2. policy requires authoritative reconciliation + current `AUTHORITATIVE_EVIDENCE` -> prerequisite passes;
3. policy requires it + `HEURISTIC_ONLY` -> fail before consumption;
4. policy requires it + `UNAVAILABLE_OR_UNVERIFIED` -> fail before consumption;
5. required evidence missing -> fail before consumption;
6. expired evidence -> fail before consumption;
7. endpoint identity drift -> fail before consumption;
8. target configuration drift -> fail before consumption;
9. verifier/policy trust-anchor mismatch -> fail before consumption;
10. capability evidence digest mismatch -> fail before consumption;
11. capability not required by policy -> existing execution contract remains unchanged;
12. post-dispatch reconciliation outage -> remain `EFFECT_UNKNOWN`, no redispatch;
13. failed eligibility check -> authorization remains unconsumed and network unused.

## 12. Non-claims

This decision does not claim:

- that every external API is reconcilable;
- that idempotency keys alone are sufficient;
- that authoritative reconciliation guarantees exactly-once delivery;
- that current runtime enforcement already exists;
- that all external actions must satisfy this prerequisite;
- that transient lookup availability must be synchronously probed before dispatch;
- production readiness; or
- regulatory approval.

## 13. Implementation boundary

Implementation is provided by the separate policy-gated profile documented in `reconciliation-capable-execution-profile-v1.md`.

That implementation:

- introduces an explicit deployment-controlled policy input;
- consumes the existing reconciliation-capability evidence through a narrowly scoped gate;
- performs the current-target/trust/freshness rechecks;
- fails before authorization consumption and transport when the prerequisite is unsatisfied;
- preserves existing `EFFECT_UNKNOWN`, retry, replacement, reconciliation, and recovery semantics;
- adds the focused proof cases above; and
- documents the resulting policy-gated execution profile while leaving the frozen proof v1 unchanged.

## 14. Resulting principle

The architecture decision is:

> **For external effects whose policy requires authoritative reconciliation, reconciliation capability is part of execution-target eligibility.**

And the fail-closed consequence remains:

> **If the required capability cannot be authoritatively established for the current target, VERITAS must not proceed to external effect.**
