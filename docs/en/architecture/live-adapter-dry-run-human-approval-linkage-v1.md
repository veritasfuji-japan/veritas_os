# Canonical Live Adapter Dry-Run Human Approval Linkage Review v1

## Purpose

This packet is a deterministic, content-addressed **Human Approval linkage
review artifact**. It accepts a re-verified, non-dispatched Authority Evidence
linkage review packet and caller-declared Human Approval reference metadata. It
then performs exact local comparisons for execution intent, adapter contract,
endpoint candidate, credential reference, target system, resource scope,
purpose, and Authority Evidence reference identifiers.

The packet answers only whether the declared references are structurally linked
to the dry-run execution path. A declared upstream approval state remains
metadata; it is not Human Approval and is not authorization.

## Determinism and validation

The builder and verifier both re-run the Authority Evidence linkage verifier.
Closed Pydantic models reject additional fields. Reference identifiers must be
unique, every required approval scope must be represented, timestamps are
normalized to UTC, and approved references must be unexpired at the explicit
review time. Matching is exact and local: there is no fuzzy matching, semantic
matching, provider lookup, evidence retrieval, filesystem access, or network
access.

Canonical JSON uses sorted keys and compact separators. Domain-separated
SHA-256 digests cover the reference bundle, binding matrix, linkage result,
ordered checks, future Bind requirements, and complete packet. The verifier
recomputes every derived value and rejects mutation, forged lineage, hash, or
identifier.

`semantic_match` from the verified source lineage is preserved exactly, but it
is never promoted into Human Approval, Authority Evidence, Bind authorization,
or execution authority.

## Security and non-effect boundary

This review:

- does **not** create or externally verify Human Approval;
- does **not** create Authority Evidence or execution authority;
- does **not** create Bind authorization or invoke Bind;
- does **not** create a BindReceipt or write TrustLog;
- does **not** dispatch the request;
- does **not** resolve endpoints or DNS;
- does **not** access credentials or embed credential material;
- does **not** construct authorization headers, tokens, or secrets;
- does **not** call a network or Webhook;
- does **not** instantiate or call a live adapter; and
- does **not** commit an operation or produce an apply-path result.

Missing, duplicate, pending, rejected, expired, incomplete, or mismatched
references fail closed and produce no packet. Successful local linkage retains
`NOT_DISPATCHED`, `NOT_BOUND`, `NOT_AUTHORIZED`, and `NOT_APPROVED` states.

## Future Bind authorization

A separate, explicit future artifact must prove real Authority Evidence and
Human Approval verification (where required), policy admissibility, runtime
risk, endpoint identity, credential and authorization-header boundaries,
idempotency, dispatch and Bind boundaries, BindReceipt and post-Bind TrustLog
boundaries, and later apply-path postconditions and rollback requirements.
This packet records those requirements but satisfies none of them.
