# Authority Evidence trust boundary

`AuthorityEvidence` is an unsigned claims representation. Its SHA-256
`evidence_hash` identifies content and can detect accidental changes, but it is
not evidence of issuer authenticity. In particular, a caller saying
`verification_result=VALID` is not verified authority.

The strict trust chain is canonical authority claims, a canonical
domain-separated signed envelope (including `signed_at`), a cryptographic
verifier using deployment-controlled keys, an independently configured
verifier allowlist, an approved signer/issuer policy, the exact
`ActionClassContract.deterministic_digest()`, actor/scope/policy context,
timezone-aware validity, and an independent fresh revocation result. Only the
all-or-nothing verifier entrypoint may emit `VerifiedAuthorityEvidence`.
Runtime revalidates its proof hash and complete context, and secure/production
posture rejects raw authority claims.

These guarantees are deliberately separate:

- Hash matches does not imply authentic authority.
- A valid signature does not imply an authorized signer.
- An authorized signer does not imply an approved deployment verifier.
- A non-revoked result records state only at its timezone-aware `checked_at`;
  yesterday's result does not establish current non-revocation.
- The same contract version does not imply the same contract content.
- `VerifiedAuthorityEvidence` is not Human Approval.
- `VerifiedAuthorityEvidence` is not Bind Authorization.
- Bind Authorization is not Bind Invocation.

The optional local Ed25519 backend accepts public keys only from
deployment-controlled configuration. Core governance imports do not require
the optional `cryptography` dependency. Selecting the Ed25519 backend without
the signing extra fails explicitly; it never degrades to successful
verification. Public keys and `verified`, `signature_verified`, `not_revoked`,
or similar flags supplied in an artifact never establish trust.

`VerifiedAuthorityEvidence` is currently process-local: its canonical proof
hash is independently rechecked, while an in-process issuance registry adds a
second provenance guard. A deserialized proof must be regenerated from the
signed artifact. The registry is additional hardening, not a substitute for
claims, contract, deployment-policy, time, scope, and revocation checks.
Production KMS/HSM and prefetched revocation services can implement the
verifier/checker protocols without changing this boundary or making network
calls here.
