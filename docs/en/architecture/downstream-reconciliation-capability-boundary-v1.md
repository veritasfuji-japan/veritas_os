# Downstream Reconciliation Capability Boundary v1

Status: **DESIGN-FIXED / NON-ENFORCING**

## 1. Purpose

VERITAS already models ambiguous external execution as `EFFECT_UNKNOWN` and
requires independently verified reconciliation before a terminal effect claim is
accepted.

This document makes one additional boundary explicit:

> The ability to reconcile an ambiguous effect is partly a property of the
> downstream execution target, not only of VERITAS.

A downstream system may not provide a durable caller-chosen correlation key, a
queryable record for one execution attempt, or another authoritative observation
surface. VERITAS must not silently replace that missing capability with heuristic
matching.

This document is intentionally non-enforcing. It does not change the frozen
controlled Decision-to-Effect proof, authorization semantics, retry semantics,
or the current definition of confirmed external effect.

## 2. Core invariant

The boundary is:

`missing authoritative reconciliation capability != proof of no effect`

Therefore:

- absence of a query result is not proof that nothing happened;
- absence of a query API is not proof that nothing happened;
- timestamp, amount, payload similarity, log proximity, or operator intuition are
  not by themselves authoritative effect evidence;
- inability to determine what happened does not create permission to retry; and
- `EFFECT_UNKNOWN` must remain unresolved unless evidence accepted by the
  configured reconciliation verifier can support a terminal claim.

The existing invariant remains unchanged:

`EFFECT_UNKNOWN -> verified reconciliation -> {CONFIRMED_EFFECT | CONFIRMED_NO_EFFECT | EFFECT_UNKNOWN}`

## 3. Capability classes

This document defines four descriptive classes for downstream reconciliation
capability. These classes are architecture vocabulary only in v1; they are not
yet runtime policy inputs.

### 3.1 `AUTHORITATIVE_QUERY`

The downstream system provides an exact read-only lookup for an execution attempt.
A strong example has all of the following properties:

- a correlation identity is chosen before dispatch;
- the identity is bound to the exact VERITAS operation / authorization /
  consumption lineage;
- the downstream system durably stores that identity with the attempted effect;
- a read-only lookup can return the record for that exact identity; and
- the returned observation can be independently verified under a configured
  verifier policy.

A caller-generated idempotency key plus an authoritative status/operation lookup
is one possible realization. The key alone is not sufficient if the downstream
system cannot later answer what happened to that exact attempt.

### 3.2 `AUTHORITATIVE_EVIDENCE`

The downstream system does not expose an exact query API, but another authoritative
observation surface can prove the effect state. Examples may include a signed
receipt, an independently verifiable event record, or an immutable ledger entry.

The evidence must still bind the exact operation lineage and pass a configured
`ReconciliationEvidenceVerifier` before it can terminalize `EFFECT_UNKNOWN`.

### 3.3 `HEURISTIC_ONLY`

The downstream system can only be correlated approximately, for example by:

- timestamp windows;
- amount/value matching;
- payload similarity;
- nearby log entries; or
- fuzzy operator search.

These signals may assist investigation, but they must not by themselves produce
`CONFIRMED_EFFECT` or `CONFIRMED_NO_EFFECT`.

### 3.4 `UNAVAILABLE_OR_UNVERIFIED`

No authoritative reconciliation surface is available, or the claimed capability
has not been verified strongly enough to rely on it.

If an execution attempt becomes ambiguous, the state remains `EFFECT_UNKNOWN`.
Blind redispatch remains prohibited.

## 4. Required properties of an authoritative reconciliation path

For VERITAS to treat a downstream reconciliation path as authoritative, the
future implementation should be able to establish at least the following:

1. **Pre-dispatch identity** — the correlation identity exists before transport
   may begin.
2. **Exact lineage binding** — the observation binds the exact operation,
   authorization, consumption, and execution intent as required by the verifier
   policy.
3. **Downstream durability** — the target or independent evidence source retains
   enough state to answer the question after the original response is lost.
4. **Read-only verification** — reconciliation does not resend the external
   effect.
5. **Verifier-controlled trust** — caller-declared success/failure is not trusted
   without independent verification.
6. **Deterministic terminalization** — only verified evidence can move an
   unresolved state to a terminal effect state.

## 5. Relationship to `EFFECT_UNKNOWN`

This boundary does not introduce a new effect state.

The existing states remain:

- `IN_FLIGHT`
- `EFFECT_UNKNOWN`
- `CONFIRMED_EFFECT`
- `CONFIRMED_NO_EFFECT`

The new distinction is about whether the selected target has a trustworthy path
for resolving `EFFECT_UNKNOWN` if ambiguity occurs.

When that path is absent or insufficient:

`EFFECT_UNKNOWN -> EFFECT_UNKNOWN`

The system must not manufacture certainty to make the workflow terminate.

## 6. Retry and replacement behavior

Lack of reconciliation capability never authorizes blind redispatch.

If an external effect may have occurred and cannot be authoritatively resolved:

- the original authorization remains consumed;
- the unresolved effect remains `EFFECT_UNKNOWN`;
- the same business event remains subject to the existing unresolved-event block;
- a replacement authorization must not be used to bypass the uncertainty; and
- recovery may escalate for investigation, but investigation alone does not become
  effect evidence unless it produces evidence accepted by the configured verifier.

Human involvement can coordinate recovery and obtain evidence. A human assertion
by itself does not retroactively prove the external effect unless the governing
contract explicitly accepts and verifies the resulting evidence form.

## 7. Execution eligibility implication

Reconciliation capability may become part of execution-target eligibility,
especially for high-risk external effects.

A future enforcing design may require a target to demonstrate an accepted
reconciliation capability before execution authority can be consumed or before
transport can begin.

That is **not** implemented by this document.

Adding such a precondition would change the controlled execution contract and
therefore requires an explicit architecture decision, focused tests, proof
updates, and human approval. It must not be introduced as an incidental refactor
or documentation-only semantic change.

## 8. Controlled proof relationship

The frozen controlled Decision-to-Effect proof already exercises a target with:

- a caller-controlled idempotency/correlation identity;
- durable downstream persistence;
- an independent read-only lookup path;
- `EFFECT_UNKNOWN` preservation during lookup outage;
- no blind redispatch; and
- verified reconciliation before terminal receipt/outcome evidence.

This document does not widen that proof claim to arbitrary enterprise endpoints.
Instead, it explains why the controlled proof cannot automatically be generalized
to a target that cannot authoritatively answer what happened.

## 9. Suggested future proof cases

If this boundary later becomes executable policy, focused proof cases should
include at least:

1. exact authoritative query -> verified terminal reconciliation;
2. temporary lookup outage -> remain `EFFECT_UNKNOWN`;
3. heuristic-only correlation -> remain `EFFECT_UNKNOWN`;
4. no reconciliation capability -> remain `EFFECT_UNKNOWN` and no redispatch;
5. stale or changed capability evidence -> fail closed before relying on it;
6. caller-declared terminal result without verifier proof -> reject;
7. replacement authorization while the original business event is unresolved ->
   reject under the existing replacement-blocking semantics.

## 10. Non-claims

This document does not claim:

- that every external API is safely reconcilable;
- that idempotency keys alone prove external effect state;
- exactly-once delivery by an external provider;
- production readiness;
- that heuristic correlation is authoritative evidence;
- that human review can reconstruct unavailable external truth; or
- that the current frozen proof has been widened to non-reconcilable targets.

## 11. Design principle

The resulting principle is:

> **Reconciliation capability is a property of the execution target and may
> constrain execution eligibility.**

And the fail-closed consequence is:

> **If VERITAS cannot authoritatively determine what happened, it must preserve
> uncertainty rather than invent certainty or retry permission.**
