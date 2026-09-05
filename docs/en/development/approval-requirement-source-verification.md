# Approval requirement source verification

`verify_human_approval_requirement_resolution_packet(packet, source, contract)`
requires the full Authority Evidence Linkage source and the expected Action
Class Contract. The one-argument, hash-only interface is no longer supported.
The verifier revalidates the source and reconstructs every field from it and
the contract. Rehashing a forged NOT_REQUIRED result cannot bypass this check.
Both the builder and verifier of requirement satisfaction use this interface.

The caller must obtain the expected contract from trusted policy configuration;
an attacker-controlled replacement contract is not a trust anchor.
The satisfaction verifier requires keyword-only `expected_source` and
`expected_contract`, compares the complete embedded source and contract to
these independently verified inputs, and derives results only from the
reconstructed resolution. Same-ID/version contract substitutions are rejected.
Final Bind Readiness and Bind Gate Review builders and verifiers propagate
these same keywords through every self-verification call. They are optional
only for the legacy v1 linkage path; a v0.3 satisfaction path fails closed when
either is absent. No embedded snapshot fallback is permitted. Further callers
that omit these inputs cannot consume a v0.3 gate; they must explicitly pass
trusted inputs before enabling that path. Never extract expected inputs from
the packet under verification.
Resolution time is a recorded timestamp, not a live freshness attestation.

## Non-effecting fresh composition

`build_fresh_bind_source_chain(..., expected_contract=trusted_contract)` selects
v0.3 requirement satisfaction. Supply the contract from trusted configuration
outside `FreshBindSourceChainInputs`; do not select it from a candidate gate.
The authority source is freshly constructed from the checked prerequisite chain.
REQUIRED needs caller-supplied human reference metadata; NOT_REQUIRED may use
`human_approval_reference_bundle=None`. No receipt is inferred. Omitting the
contract retains legacy v1 composition.

Pass `result.authority_linkage_packet` and that same trusted contract as
`expected_source` and `expected_contract` to
`derive_verified_real_bind_context_hash(result.verified_gate_review_packet, ...)`.
The helper reverifies the whole gate before deriving its context digest.
Missing anchors or same-ID/version policy substitution fail closed for v0.3.
This composition itself remains non-effecting. The separate approval and
authorization issuers accept v0.3 with the independent inputs described below.
No trusted policy registry, credential access, or execution capability is added.

## Explicit v0.3 issuance inputs

`issue_gate_bound_human_approval_artifact` accepts `expected_source` separately
from the gate and uses its existing `action_contract` argument as trusted policy.
An explicit approval event, matching approval reference and deployment signer
remain mandatory. NOT_REQUIRED does not generate or infer a Human Approval Receipt.

For Bind authorization, set `RealBindAuthorizationGovernanceInputs.expected_source`
to the independently acquired authority linkage source and `action_contract` to
the trusted contract. The decision-to-authorization entry point, authorization
builder, verifier and governance context derivation propagate those same inputs.
Do not populate either from embedded snapshots in an untrusted gate or artifact.
Legacy v1 inputs remain compatible; missing anchors fail closed for v0.3.

These are prerequisites, not a replacement for signed authority verification,
revocation/freshness checks, required signed Human Approval, explicit authorizer
GO, approved issuer identity or signature checks. Local tests use ephemeral keys
and real Ed25519 verification. Issuance produces an unconsumed authorization;
it does not invoke Bind, resolve credentials, dispatch requests or create effects.

## Consumption-time governance recheck

The temporal validator separates two evaluations. `governance_inputs.verification_now`
reconstructs and verifies the signed issuance proofs unchanged. After checking
the authorization validity window, it revalidates the same independent source,
contract, signed authority and required Human Approval at the explicit consumption
`now`, including revocation freshness and runtime-authority evaluation. New
time-dependent proof hashes are not compared to or written over historical hashes.
Backdating consumption before the issuance verification time is rejected.

The caller must obtain `now` from its trusted execution clock, not packet data.
This function does not authenticate a caller's clock or re-read policy from a
registry. Independent trust inputs and live verification dependencies remain the
deployment's responsibility. Any failed recheck stops before consumption and
credential resolution; no historical pass can substitute for the new evaluation.

Local v0.3 integration tests connect issued authorization to single-use consumption,
Bind adjudication, OutcomeReceipt lineage and effect-state recording. They use
ephemeral signing keys, in-memory stores, a synthetic adapter/credential provider,
and a fake TrustLog sink. Blocked apply records CONFIRMED_NO_EFFECT; a successful
generic apply remains EFFECT_UNKNOWN without an independently verified external
acknowledgement. These tests do not prove live /v1/decide-to-effect integration,
durable production audit storage or a real customer operation.

Requirement-resolution integration tests exercise the nested metadata chain without
mocking its verifier. They do not claim cryptographic authority authentication.
Authority signature/revocation verification and human approval verification
remain separate boundaries. The requirement-resolution layer creates no authority.

## Real decision connection: remaining source boundary

`issue_verified_real_decision_bind_authorization` now reconstructs the intent
with the existing canonical, content-addressed promotion builder. The previous
generic promotion helper allocated a new UUID on each invocation, making exact
comparison with a previously constructed source intent impossible. Policy
freshness uses the independently supplied `governance_inputs.verification_now`.
The policy ID and optional approval context are assertions against the verified
promotion; caller policy-lineage overrides remain forbidden.

An isolated HTTP integration test invokes the real authenticated `/v1/decide`
route, kernel, compiled-policy signature verification and CDA construction.
Only model output and cloud clients are controlled. The returned CDA and chosen
candidate are used unchanged by canonical promotion, readiness, pre-bind,
preflight and native adapter selection. No benchmark expected outcomes or
accepting packet-verifier doubles supply this lineage.

This test exposes an unfinished connection, not a completed execution proof:
`build_fresh_bind_source_chain` still accepts handoff-native adapter selection;
it rejects the promotion-native selection format even when a trusted contract
is supplied. A separately valid v0.3 fixture gate is also rejected because its
intent differs from the real decision. The tests require both refusals before
authorization signing. They do not issue an authorization, create a Human
Approval Receipt, consume credentials, invoke an adapter or create Bind/outcome
receipts for this real decision.

The next implementation must preserve the native promotion source through
requirement resolution/satisfaction and the authorization verifier, including
independent source/contract anchors. It must not relabel native packets as
handoff packets or synthesize handoff replay/approval evidence to satisfy the
older schema. Existing fixture-based v0.3 consumption tests remain separate
from this real-decision connection test.
