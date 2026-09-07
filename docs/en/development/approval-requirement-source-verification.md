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

## Real decision connection: source boundary identified in #2189

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

Further integration must preserve the native promotion source through
the authorization verifier, including independent source/contract anchors.
It must not relabel native packets as
handoff packets or synthesize handoff replay/approval evidence to satisfy the
older schema. Existing fixture-based v0.3 consumption tests remain separate
from this real-decision connection test.

## Native source requirement resolution and satisfaction

The HARR builder/verifier now dispatches explicitly on the Authority Evidence
Linkage source format and invokes the corresponding full native or legacy
verifier. It retains the original source identity/hash; no handoff fields are
invented. Native resolution cannot predate its source. Legacy packet identity
and verification semantics are preserved.

`build_promotion_human_approval_requirement_satisfaction_packet` connects this
rebuilt resolution to native Human Approval linkage. REQUIRED needs a verified
native linkage with the exact same complete authority source; NOT_REQUIRED
requires no linkage. Both states are metadata evidence only, with
`human_approval_proven=false` and `ready_for_real_bind=false`.

`verify_promotion_human_approval_requirement_satisfaction_packet` requires
keyword-only `expected_source` and `expected_contract` from independent trusted
inputs. It reconstructs every field, including the full source, contract snapshot,
contract digest, intent and requirement state, and returns the rebuilt packet.
Embedded snapshots are never trust anchors. Fully rebuilt and rehashed same-ID/
version contract substitutions and source/linkage substitutions are rejected.

Real authenticated `/v1/decide` integration now reaches native authority linkage,
HARR and satisfaction for both required and not-required inputs. The existing
native linkage rule still requires the candidate's declared approval flag on
the REQUIRED path; no flag is changed in returned CDA/candidate data. Model/cloud
clients and reference metadata remain controlled test inputs. No Human Approval
Receipt or execution authority is produced by this new boundary.

This is a distinct native packet (`promotion-human-approval-requirement-satisfaction/v1`),
not a relabeled legacy satisfaction packet. The dedicated requirement-aware
Final Readiness/Gate path below consumes it. The legacy fresh-source
format-refusal test remains valid.

## Requirement-aware native Final Readiness and Gate

`promotion_requirement_bind_readiness` connects verified satisfaction to
`PromotionRequirementFinalReadinessPacket` and `PromotionRequirementBindGatePacket`.
Every builder and verifier requires independent `expected_source` and
`expected_contract`. Gate verification propagates those inputs through readiness,
satisfaction, and resolution; no embedded snapshot becomes a trust anchor.
All derived fields are reconstructed, and verifiers return the rebuilt objects.
The complete source chain retains the original intent, endpoint, credential scope,
authority linkage, and optional human linkage without synthesizing legacy fields.

Both REQUIRED and NOT_REQUIRED states are supported. Conditional future human
approval requirements come only from the verified resolution; other authorization
and invocation prerequisites remain outstanding. Rejected readiness cannot enter
Gate review. Rejected Gate review remains fail-closed. Local review acknowledgements
are explicit metadata, not signed Human Approval Receipts.

The separate closed schemas preserve existing linkage-only native v1 and legacy
v0.3 APIs. Real authenticated `/v1/decide` tests reach the new Gate for both states
with controlled model/cloud clients. Fully rehashed source/policy substitutions
under identical contract ID/version are rejected at both review boundaries.

The new Gate feeds the requirement-aware fresh verification and final rechecks
described below. No authorization, credential access, network dispatch, or
external effect is created by these review stages.

## Fresh source verification and final metadata rechecks

`promotion_requirement_final_rechecks` consumes the verified requirement-aware
Gate without converting it into the older linkage-only packet format.
`PromotionRequirementFreshSourcePacket` re-verifies the full Gate chain against
independent source and contract inputs, then derives an exact Bind context
committing the Gate hash, authority source, requirement resolution, contract,
intent, adapter, endpoint and credential bindings. Its verifier also requires
the independently supplied verification time. A failed Gate cannot enter.

`PromotionRequirementFinalRecheckPacket` consumes this rebuilt fresh packet and
compares caller-supplied current endpoint metadata, credential reference and
required credential scope with the fully verified source. All metadata must
match exactly; scope containment is never inferred. Its verifier requires the
same independent anchors and current metadata, plus the expected recheck time.
Embedded endpoint/reference/time fields cannot substitute for these inputs.
Changing endpoint identity or credential scope rejects an otherwise valid old
packet. Rehashed context, source, same-ID/version contract, or time substitutions
are also rejected. Both verifiers return rebuilt results.

The fresh packet consumes fresh verification and exact context derivation;
the final packet consumes endpoint and credential rechecks in that order.
Remaining authorization work begins with runtime risk review. Approval-related
future requirements remain conditional on the verified ActionClassContract;
invocation requirements remain unchanged and unsatisfied.

These are local metadata checks. Fresh verification does not establish live
policy freshness or revocation status. Endpoint recheck does not contact a
server or verify a TLS peer. Credential recheck does not access a credential
provider or prove that its actual permissions match its reference metadata.
All such claims and `ready_for_real_bind` remain false.

Real authenticated `/v1/decide` tests reach final metadata rechecks for both
approval states with controlled model/cloud clients and explicit test metadata.
The older native and legacy APIs remain unchanged. The requirement-aware
runtime-risk boundary below consumes the final packet. Authorization issuance,
real-decision single-use execution and outcome validation are separate boundaries;
native v2 issuance and consume-only boundaries are described below. Integration
with action execution and outcome validation remains incomplete.

## Runtime-risk review from verified final rechecks

`promotion_requirement_runtime_risk` re-verifies the complete independently
supplied final recheck using trusted source/contract, current endpoint/credential
metadata, required scope, and expected verification/recheck times. Its compact
packet references the exact source hash, Bind context, policy and intent.
The full source is required separately for verification; it is not embedded.

The review must bind that exact source/context/contract and the intent's expected
state fingerprint. The existing runtime-risk evaluator is shared with the older
native path: negative risk or state drift blocks; missing risk, state evidence,
or TTL is indeterminate and fail-closed. The review window is at most 300 seconds
and must fit within the intent's TTL for PASS. Verification also requires an
independent expected risk decision, expected record time, and current time;
an unchanged packet is rejected at or after review expiry. Embedded review
evidence cannot replace the external expected decision.

`require_promotion_requirement_runtime_risk_pass` returns only rebuilt PASS
results and rejects BLOCK or INDETERMINATE before later composition. Only PASS
consumes the runtime-risk requirement. Other authorization and all invocation
requirements remain outstanding, including the independent Bind-time risk check.
The native v2 authorization issuer below calls this guard before issuance.

Risk signals, observed state and evidence references are caller-supplied inputs,
not authenticated sensor results. This boundary neither obtains nor invents
them. Real authenticated API tests explicitly supply TTL and synthetic state
at the supported promotion boundary for PASS cases, without editing returned
CDA/candidate data; cases without that metadata remain indeterminate. Controlled
model/cloud clients and synthetic runtime observations are test fixtures only.
No Human Approval Receipt, execution authority, Bind authorization, credential
access, network dispatch, BindReceipt, or external effect is produced.

## Native authorization v2 (issuance only)

`native_bind_authorization.issue_native_bind_authorization` composes this PASS
guard with existing cryptographic Authority Evidence, revocation, signed Human
Approval Receipt, RuntimeAuthority, signed GO decision, grant and idempotency
checks. The complete final recheck and independent expected review, times and
current metadata are mandatory `NativeAuthorizationSourceInputs`. Trusted
Authority Evidence Linkage source, ActionClassContract and verification clock
come independently from `RealBindAuthorizationGovernanceInputs`, never from an
embedded snapshot. Only rebuilt verifier outputs feed downstream derivation.

The issuer requires an existing signed receipt for REQUIRED and rejects supplied
receipts for NOT_REQUIRED. It creates no human approval. Authority/receipt/GO
signatures use the existing deployment-owned verifier policies. The GO signer
must differ from both gate and risk reviewers. The authorization validity window
must fit the current risk review, intent and signed evidence windows.
Only boolean `required` and integer `minimum_approvals` (0 or 1) are supported
here. Quorum requirements and additional approval rules are rejected, not
silently treated as satisfied by a single receipt.

The closed `native-live-adapter-bind-authorization/v2` artifact preserves native
source hashes and signs all fields using a distinct v2 domain. Its internal
context projection only reuses existing check interfaces: it is not a fabricated
legacy packet and contains no invented handoff/replay evidence. Ed25519 issuer
verification requires explicit `authorization_artifact_version="v2"` and a
matching deployment policy hash. The default v1 verifier and v1 artifact schema
reject v2; existing v1/v0.3 paths are retained.

`verify_native_bind_authorization` re-verifies signatures and reconstructs every
field at the independently supplied issuance verification time. This is not a
consumer or a current execution permission. The consume-only API below performs
the independent current-time checks.
Idempotency commits the signed decision/context, risk hash, contract and window;
single-use policy is signed, but unused-key status is **not** proven. Atomic
consumption is implemented separately below; fresh Bind-time governance/risk checks
remain mandatory for future execution. No credential resolution, header construction, network, Bind invocation,
BindReceipt or external effect is performed by this issuance boundary.

Test keys and signed authority/approval artifacts are synthetic; they do not
represent operational human consent. Caller risk evidence remains unauthenticated
sensor input, and the injected cryptographic backends must be non-effecting.

## Native v2 consume-only boundary

`consume_native_bind_authorization` verifies the unchanged signed issuance
artifact with independent issuance inputs, rejects backdated/expired clocks,
then reconstructs the current source from separately supplied source/risk inputs.
The fresh review and record times must equal the trusted consumption time.
BLOCK, INDETERMINATE, drift, missing inputs and reused issuance reviews fail
before storage. Exact intent, Bind context, gate and contract must match the
signed authorization. Original authority and required human receipt signatures,
revocation status and RuntimeAuthority are reverified at consumption time.
Historical signed proof hashes remain unchanged; current proofs are returned
separately. Caller-supplied observations are still not authenticated sensors.

The existing PostgreSQL store atomically records one consumption using unique
authorization-ID and idempotency-key constraints. The existing record schema
can carry native `laba:v2` IDs without fabricating legacy source data. PostgreSQL
is required by default; in-memory storage requires explicit test-only opt-in and
is reported as non-durable. Unknown stores cannot self-assert production safety.
Duplicate attempts and failed/ambiguous store acknowledgements return no success.
No consumption is released after failure, including commit followed by lost ACK.

The only intended write is the configured consumption database. No action
credential, authorization header, adapter, Bind invocation, BindReceipt or
external-action dispatch is involved. The consumption result is audit lineage,
not a reusable execution capability. The supplied clock establishes validation
time, not database commit time; future action execution must recheck current
policy/risk and durable consumed lineage rather than trusting a saved result.
Both approval states have real-verifier tests and PostgreSQL contention tests
in the existing database CI job; this does not claim production deployment or
completed decision-to-external-effect integration.
