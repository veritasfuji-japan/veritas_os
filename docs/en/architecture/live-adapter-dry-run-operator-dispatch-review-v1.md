# Canonical Live Adapter Dry-Run Operator Dispatch Review v1

## Purpose

The Canonical Live Adapter Dry-Run Operator Dispatch Review Packet is a
deterministic, content-addressed **operator dispatch review artifact**. It
answers whether an identified operator explicitly reviewed a verified,
credential-authorized, non-dispatched candidate, including its endpoint
allowlist evidence, credential authorization evidence, scope limitations, and
non-effect guarantees.

An approved packet permits progression only to a **separate future Bind
pre-dispatch review artifact**. It does not authorize execution or Bind by
itself. `REJECT` and `HOLD_FOR_MORE_EVIDENCE` decisions remain fail-closed.
Human maintainer approval remains required for this governance-sensitive
boundary.

## Inputs and deterministic verification

The builder accepts a Canonical Live Adapter Dry-Run Credential Authorization
Evaluation Packet v1, an explicit closed-schema operator decision, and a
caller-supplied recording timestamp. Both the builder and verifier reverify the
embedded credential authorization packet. They require an authorized source
whose state and status remain non-dispatched, and exact matches for the
endpoint, credential reference, adapter contract, target system, and target
resource scope identities.

Canonical JSON uses sorted keys and compact separators. Domain-separated
SHA-256 digests bind the decision, review binding, ordered checks, future
requirements, and complete packet. Timestamps are normalized to UTC. No UUID,
random value, current time, environment state, filesystem state, or external
provider contributes to verification.

`semantic_match` is copied exactly through the source evidence lineage. It is
not promoted to Authority Evidence, Human Approval, Bind authorization, or
execution authority. Either semantic-match value can be recorded locally when
the canonical source packet otherwise verifies.

## Security and non-effect boundary

This artifact:

- does **not** dispatch the request;
- does **not** invoke Bind;
- does **not** create a BindReceipt;
- does **not** write TrustLog;
- does **not** resolve an endpoint or perform DNS resolution;
- does **not** resolve or access credential material;
- does **not** embed credentials, tokens, or secrets;
- does **not** construct authorization headers;
- does **not** call the network or Webhook;
- does **not** instantiate or call a live adapter;
- does **not** commit an operation; and
- does **not** authorize execution by itself.

Every ordered check repeats false effect flags. The packet-level state is
`NOT_DISPATCHED`, and all effect booleans are fixed to `false`. Mutation of the
source, decision, bindings, checks, future requirements, lineage, scope
limitations, packet hash, or content-addressed ID is rejected.

> **Security warning:** Approval here is only permission to advance evidence
> to another review boundary. Treating this artifact as dispatch or Bind
> authority would violate its fail-closed contract.

## Future Bind pre-dispatch review

This packet records, but does not satisfy, requirements for a separate future
artifact. Before any future dispatch, that artifact must prove:

1. Bind pre-dispatch policy review;
2. Authority Evidence recheck;
3. Human Approval boundary verification, when applicable;
4. endpoint identity recheck;
5. credential authorization recheck;
6. credential-material resolution boundary;
7. authorization-header construction boundary;
8. network dispatch boundary;
9. request dispatch receipt boundary;
10. TrustLog write boundary after proper authorization;
11. BindReceipt boundary only after Bind; and
12. rollback and postcondition requirements for a later apply path.

Each requirement states both `separate_future_artifact_required: true` and
`satisfied_by_this_packet: false`. Consequently, even an
`APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW` decision can set `fail_closed` to false
only for progression to that future review; it cannot cross any execution or
external-effect boundary.
