# Bind → Outcome → TrustLog Lineage v1

## Purpose

This boundary closes the post-bind evidence chain after a Real Bind Authorization has been atomically consumed.

The chain is:

`Real Bind Authorization → Authorization Consumption → Bind Core → BindReceipt → OutcomeReceipt → TrustLog`

The implementation reuses the existing authorization-consumption gate, BindReceipt hashing/TrustLog helpers, and deterministic OutcomeReceipt artifact.

## Exact lineage

The final BindReceipt governance identity records non-secret references to:

- Real Bind Authorization ID and hash;
- authorization decision digest;
- authorization issuer verifier-policy hash;
- authorization consumption ID and hash;
- consumption timestamp and idempotency key;
- single-use enforcement status;
- Bind-core invocation status;
- adapter-apply-attempt status.

The OutcomeReceipt then binds:

- decision ID;
- ExecutionIntent ID;
- BindReceipt ID and hash;
- BindReceipt TrustLog hash;
- Real Bind Authorization ID/hash;
- authorization consumption ID/hash;
- bind-context hash;
- idempotency key;
- final Bind outcome;
- pre/post state fingerprints when available;
- rollback/failure information;
- whether adapter apply was attempted.

The OutcomeReceipt has its own deterministic `outcome_hash` and is appended to TrustLog after the linked BindReceipt.

## Effect semantics

A generic `BindAdapterContract.apply()` call is **not** sufficient evidence that an external effect occurred. An adapter may represent local memory, a database, a provider SDK, hardware, or a network request.

Therefore this boundary preserves the distinction:

- Authorization != Consumption
- Consumption != Bind-core entry
- Bind-core entry != Adapter apply
- Adapter apply != Proven external effect
- BindReceipt != OutcomeReceipt
- OutcomeReceipt != External-system acknowledgement

`observed_effects` records only the adapter-apply attempt unless a concrete adapter provides stronger effect evidence in a later boundary.

## TrustLog ordering

The composed path calls the authorization-consumption gate with Bind TrustLog writing disabled. This prevents a partially enriched BindReceipt from being logged. After Bind returns:

1. ExecutionIntent is appended;
2. the BindReceipt is enriched with authorization/consumption lineage and appended once;
3. the OutcomeReceipt is created from that persisted BindReceipt;
4. the OutcomeReceipt is appended.

This yields an explicit evidence path from the consumed authorization to the post-bind outcome.

## Important failure boundary

TrustLog persistence happens after the Bind attempt. A storage failure can therefore occur after adapter apply has been attempted. The implementation raises `BOL_TRUSTLOG_PERSISTENCE_FAILED_AFTER_BIND_ATTEMPT` and does **not** pretend that no effect occurred. The consumed authorization remains consumed.

This PR deliberately does not solve crash recovery or ambiguous external-effect state. Those belong to the next boundary:

`IN_FLIGHT / EFFECT_UNKNOWN → reconciliation → terminal outcome`.

## Non-claims

This boundary does not claim:

- exactly-once external effects;
- proof that a generic adapter apply reached an external system;
- recovery from process death between apply and TrustLog persistence;
- external-system acknowledgement;
- reconciliation of timeout/unknown outcomes.

Those are separate runtime/reconciliation concerns and must not be inferred from a successful BindReceipt or OutcomeReceipt.
