# CanonicalDecisionHandoff v1 runtime validator

The standalone validator is a deterministic, side-effect-free, fail-closed
boundary. It accepts an untrusted handoff, independently supplied trusted
assertions, and a timezone-aware evaluation time. It stops after reporting a
validation status; `READY_FOR_GUARDED_PROMOTION` is only eligibility for a
future guarded promotion attempt and is not execution authority.

## What it verifies

The validator checks runtime-critical structure, canonical decision fields,
request and decision lineage, exact candidate/target consistency, structured
actions, Authority and Human Approval evidence bindings and time intervals,
policy freshness, expected-state presence and future timestamps, provenance
values, trusted assertion bindings, and the separately trusted
`CandidateHashBindingAssertion`. Expected state is conservatively mandatory
for READY in validator v1 because no typed authoritative exemption exists.

Assertion values use the domain-separated profile
`veritas.canonical-handoff.assertion-value/v1`. This local digest prevents an
assertion for value A from being reused for value B. It is **not** a candidate,
decision, evidence, receipt, TrustLog, replay, or other artifact/domain hash.
The validator never computes the opaque domain-level candidate hash; it only
checks that a trusted upstream binding names the exact candidate and supplied
hash.

Validation proceeds through structure, structural refusal, intrinsic semantic
consistency, required review, missing prerequisites, independent provenance,
and finally READY. Declared `handoff_status` and `refusal_reason_codes` are read
only to report whether they match the independently computed result. Positive
self-asserted verification never creates trust; negative self-assertions may
deny readiness.

## Explicit non-claims

The validator does not query live IAM, verify issuer cryptography, query a
Human Approval backend, policy provider, or target state, produce canonical
decision/candidate hashes, produce `/v1/decide` lineage, establish execution
authority or Bind admissibility, create an `ExecutionIntent`, invoke candidate
promotion or Bind, write TrustLog, execute an action, or perform network or
filesystem I/O. A future consumer must independently supply authentic trusted
assertions and undergo separate review before any promotion can be wired.
