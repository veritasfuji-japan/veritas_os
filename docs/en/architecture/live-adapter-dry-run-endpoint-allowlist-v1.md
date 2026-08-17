# Canonical Live Adapter Dry-Run Endpoint Allowlist Evaluation v1

## Purpose

This packet is a deterministic, content-addressed **endpoint allowlist evaluation
artifact**. It answers whether a declared endpoint candidate exactly matched an
active entry in a caller-supplied local allowlist snapshot after the source
non-dispatched dispatch-readiness packet was verified.

Comparison is exact and local. It does not use fuzzy matching, redirects, CNAMEs,
or semantic similarity. `semantic_match` from the source lineage is preserved,
but is not used by the comparison and is not promoted to Authority Evidence,
Human Approval, or execution authority. A mismatch is recorded with
`fail_closed: true` rather than authorizing any action.

## Security and non-effect boundary

The implementation only validates caller-provided data and computes canonical
JSON SHA-256 digests. It:

- does not resolve endpoints or perform DNS lookup;
- does not call a network endpoint or Webhook;
- does not resolve, access, or embed credentials, tokens, cookies, secrets, or
  authorization headers;
- does not instantiate or call a live adapter;
- does not invoke Bind or create a BindReceipt;
- does not write TrustLog, a filesystem, or a database;
- does not dispatch or commit an operation; and
- does not authorize dispatch, satisfy Authority Evidence, or satisfy Human
  Approval.

An allowlist match proves only an exact comparison against the supplied snapshot.
It is not a claim that an endpoint exists, is safe, is controlled by an intended
party, or is suitable for production, customer, or regulatory use.

## Determinism and integrity

Candidate, snapshot, result, identity binding, ordered checks, future credential
requirements, and the packet use separate hash domains. JSON encoding uses sorted
keys and compact separators, and timestamps are normalized to UTC. The snapshot
hash covers every snapshot field except its own hash. The verifier re-verifies the
embedded dispatch-readiness packet and recomputes all derived values, hashes, and
the `ladrea:v1:sha256:` identifier.

## Deferred credential gate

Future credential resolution requires a separate explicit artifact. That future
artifact must address resolution authorization, source identity, scope binding,
non-embedding, authorization-header construction and redaction boundaries,
operator/human credential review, Bind pre-dispatch review, and the separate
network dispatch boundary. This packet records those requirements but satisfies
none of them.
