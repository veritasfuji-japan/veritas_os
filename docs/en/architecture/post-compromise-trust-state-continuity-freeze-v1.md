# Post-Compromise Trust-State Continuity Freeze v1

Status: **FROZEN PREREGISTRATION SCOPE**

Machine-readable contract:
[`docs/architecture/post-compromise-trust-state-continuity-freeze-v1.json`](../../architecture/post-compromise-trust-state-continuity-freeze-v1.json)

## 1. Purpose

This document preregisters TASK-031 before Product semantics change.

The question is deliberately narrow:

> Can historical operational state be restored after compromise or rollback without silently restoring historical execution authority, revoked credentials, revoked authority, stale Human Approval, or stale trust assumptions?

This is not a production disaster-recovery claim. It is a bounded proof contract.

## 2. Core invariants

The proof must preserve:

```text
Operational rollback != Trust rollback
Historical State != Current Authority
Recovered service health != Execution permission
```

Historical snapshot data may establish lineage.

It must not, by itself, establish current credential validity, current authority, current approval validity, current policy admissibility, or current authorization usability.

## 3. Recovery-state model

The initial proof model distinguishes operational recovery from trust validity.

```text
OPERATIONALLY_RECOVERED / TRUST_NOT_REVALIDATED
OPERATIONALLY_RECOVERED / TRUST_REVALIDATING
OPERATIONALLY_RECOVERED / TRUST_REVALIDATED
OPERATIONALLY_RECOVERED / TRUST_INVALID
```

Only the `TRUST_REVALIDATED` state may become eligible for a newly qualified execution path.

Operational health alone is never sufficient.

## 4. Trust generation / recovery epoch

The proof may use an explicit monotonic trust generation or recovery epoch.

Illustrative example:

```text
snapshot trust_generation = 41
current trust_generation  = 42
```

Generation-41 authorization, approval, or credential binding must not become generation-42 execution permission merely because the snapshot was restored.

The exact production mechanism is not frozen yet. The safety property is.

## 5. Current-state observations required before execution

Before any new post-recovery execution permission can exist, the proof must freshly establish:

1. current authority / revocation state;
2. current credential-provider state;
3. current credential scope / endpoint binding;
4. current policy state;
5. current Human Approval validity where required;
6. current execution-intent / action binding;
7. authorization identity and consumption state;
8. unresolved external-effect state, including `EFFECT_UNKNOWN`.

If any required current observation is unavailable, ambiguous, stale, or conflicting, the path fails closed.

## 6. Frozen initial scenario corpus

The initial proof corpus is:

1. **Unchanged trust after rollback**  
   Historical state is restored and current trust still matches. Fresh revalidation remains mandatory before a new execution path may qualify.

2. **Credential revoked after snapshot**  
   Snapshot says valid; current provider says revoked. Reject.

3. **Authority revoked after snapshot**  
   Snapshot contains valid authority; current authority source rejects it. Reject.

4. **Human Approval invalidated or expired after snapshot**  
   Historical approval exists but is no longer valid. Reject or require a new approval according to the action contract.

5. **Credential version changed after snapshot**  
   Historical material is not restored or reused. Current provider resolution is required.

6. **Trust-generation mismatch**  
   Historical authorization / approval bindings are non-executable under the new generation.

7. **Current trust evidence unavailable or ambiguous**  
   Missing or indeterminate current trust evidence fails closed.

8. **Policy changed after snapshot**  
   Current policy wins over historical admissibility.

9. **Historical authorization replay after recovery**  
   Old consumed / stale authorization remains rejected.

10. **Fresh requalification after recovery**  
    Current authority, policy, approval, credential and action context all pass. A newly issued authorization may qualify under the ordinary execution boundary.

## 7. External-effect continuity

Recovery must preserve the current no-blind-retry rule.

If a pre-recovery action remains unresolved:

```text
EFFECT_UNKNOWN
```

rollback does not convert uncertainty into failure, and does not create redispatch authority.

Read-only reconciliation remains required before the external outcome may be asserted.

## 8. Evidence requirements

Each scored run should preserve:

- exact tested source SHA;
- protocol / corpus version;
- snapshot identity;
- historical and current trust generation;
- authority / revocation observation;
- credential reference and non-secret resolution evidence;
- policy / approval state;
- authorization identity and consumption state;
- recovery classification;
- allow / block reason code;
- runtime-record hashes; and
- any reconciliation evidence used.

The runtime path must not receive the offline expected label before execution.

## 9. Relationship to TASK-029

TASK-029 asks where revocation linearizes relative to authorization consumption and execution commitment.

TASK-031 asks whether current trust survives historical rollback and post-compromise recovery.

These are related but not interchangeable.

## 10. Existing reusable primitives

The existing repository already contains primitives that may be reused:

- fresh governance rechecks;
- PostgreSQL single-use consumption;
- credential resolution;
- endpoint / scope binding;
- durable external-effect state;
- `EFFECT_UNKNOWN`;
- read-only reconciliation; and
- crash recovery.

Reuse does not mean the stronger post-compromise trust-state claim is already proven.

## 11. Explicit non-claims

Even a passing bounded proof would not establish:

- production disaster-recovery readiness;
- universal incident-response correctness;
- production IAM / KMS / HSM trust;
- independent ultimate trust-root legitimacy;
- production customer credential-lifecycle correctness;
- HA / DR / SLA compliance;
- third-party certification; or
- regulatory approval.

## 12. Implementation gate

No Product semantics should be changed for TASK-031 before this preregistration scope is merged.

After merge, implementation should be the minimum needed to execute the frozen corpus and prove or falsify the stated invariants.
