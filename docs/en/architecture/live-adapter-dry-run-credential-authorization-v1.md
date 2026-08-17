# Live Adapter Dry-Run Credential Authorization Evaluation v1

## Purpose

The Canonical Live Adapter Dry-Run Credential Authorization Evaluation Packet
is a content-addressed **credential authorization evaluation artifact**. It
answers whether a metadata-only credential reference exactly matches an active
entry in a deterministic local credential policy snapshot for the verified
adapter, endpoint, target system, target resource, and purpose.

The source must be a verified, matched, non-dispatched Endpoint Allowlist
Evaluation Packet. Both the builder and verifier re-verify that embedded source.
The comparison is exact and local: casing, spelling, identifiers, scopes,
environment, resource, and purpose are never fuzzily or semantically matched.

## Security and non-effect boundary

This packet does **not**:

- resolve credentials or access credential material;
- read secrets, credential payloads, environment variables, or credential stores;
- construct authorization headers or embed tokens, secrets, cookies, passwords,
  or private keys;
- resolve endpoints or DNS, call a network, or dispatch a request;
- call Webhook or instantiate or call a live adapter;
- invoke Bind, create a BindReceipt, or write TrustLog;
- authorize dispatch by itself, commit an operation, or produce external effects;
- satisfy Authority Evidence or Human Approval; or
- make production, customer, or regulatory claims.

Every ordered check carries explicit false effect flags. Unauthorized or
unmatched references remain `fail_closed=true`. An authorized result only means
that all declared metadata exactly matched an active local policy entry; it is
not execution authority and it does not expose or prove possession of a secret.

## Determinism and integrity

Canonical JSON uses sorted keys and compact separators. Timestamps are
normalized to UTC. Domain-separated SHA-256 digests bind the credential
reference, policy snapshot, result, scope binding, checks, future requirements,
and final packet. No UUID, random value, current verifier time, filesystem read,
database, provider, environment lookup, or network call participates.

The verifier re-verifies the source packet and recomputes every derived object,
digest, packet hash, and content-addressed ID. Mutated source fields, credential
metadata, policy entries, outcomes, matched entry IDs, checks, future
requirements, scope limitations, hashes, and IDs are rejected.

## Semantic divergence

The source `semantic_match` value is preserved through the copied replay
summary for lineage. It is never used for credential authorization and is not
promoted into Authority Evidence, Human Approval, or execution authority. Both
`semantic_match=true` and `semantic_match=false` remain source facts only;
source verification failure still rejects the packet.

## Required future dispatch review

This artifact records, but does not satisfy, requirements for a separate future
artifact proving:

1. operator/human dispatch review;
2. Bind pre-dispatch review;
3. endpoint identity recheck;
4. credential material resolution boundary;
5. authorization header construction boundary;
6. credential redaction boundary;
7. network dispatch boundary;
8. request dispatch receipt boundary;
9. TrustLog write boundary after proper authorization;
10. BindReceipt boundary only after Bind; and
11. rollback and postcondition requirements for a later apply path.

Future dispatch therefore requires a separate explicit artifact and all proper
authorization boundaries. This evaluation alone must never be treated as
permission to access a credential or dispatch a request.
