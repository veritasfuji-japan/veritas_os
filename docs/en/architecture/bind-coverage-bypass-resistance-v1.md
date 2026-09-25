# Bind Coverage Bypass Resistance V1

Status: **ARCHITECTURE FROZEN — IMPLEMENTED — NOT PROVEN**

Rule-of-One: `BIND_COVERAGE_BYPASS_RESISTANCE_V1`

The frozen scope contains exactly three VERITAS-owned effect boundaries:
registered Webhook ACTION, registered Webhook COMPENSATION, and native-v2
Sandbox ACTION. The executable registry, rather than this prose, is the source
of exact runtime identities and bindings.

Each sink requires a process-local, non-copyable, non-serializable, single-use
`BoundExecutionPermit` bound to the exact `ImmutableFinalDispatch`. Permit state
is held by the authority and atomically moves from ACTIVE to CONSUMED. Webhook
compensation additionally requires a single-use
`CompensationEligibilityGrant` derived from the consumed parent ACTION during
the Bind-core rollback transition. Recovery has no minting interface.

Secret material occupies only a validated authorization slot. It cannot modify
the method, endpoint, framing, bound headers, body, operation, dispatch kind, or
idempotency identity. The body bytes checked by the Permit are the same frozen
bytes handed to the production transport.

## Threat boundary and non-claims

V1 establishes only process-local capability integrity under the reviewed
VERITAS runtime interfaces. It does not claim resistance to equivalent-
privilege arbitrary code execution, monkeypatching, module replacement,
authority modification, arbitrary memory writes, interpreter/native-extension
compromise, or OS/kernel compromise.

It does not establish universal production readiness, future-path coverage,
coverage of all VERITAS external I/O, internal control-plane coverage,
customer-environment correctness, certification, universal exactly-once
delivery, remote-effect authenticity, TLS/provider proof, or external PoC
completion. A successful implementation PR remains NOT PROVEN until the exact
merged-main SHA workflow artifact is retained and independently audited.
