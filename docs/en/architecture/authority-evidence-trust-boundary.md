# Authority Evidence trust boundary

`AuthorityEvidence` is an unsigned claims representation. Its SHA-256
`evidence_hash` identifies content and can detect accidental changes, but it is
not evidence of issuer authenticity. In particular, a caller saying
`verification_result=VALID` is not verified authority.

The strict trust chain is canonical authority claims, a domain-separated
signature checked against deployment-controlled keys, signer/issuer policy,
the exact `ActionClassContract.deterministic_digest()`, actor/scope/policy
context, timezone-aware validity, and an independent revocation result. Only
the all-or-nothing verifier entrypoint may emit `VerifiedAuthorityEvidence`.
Runtime revalidates its proof hash and context, and secure/production posture
rejects raw authority claims.

These guarantees are deliberately separate:

- Hash matches does not imply authentic authority.
- A valid signature does not imply an authorized signer.
- An authorized signer does not imply current non-revocation.
- `VerifiedAuthorityEvidence` is not Human Approval.
- `VerifiedAuthorityEvidence` is not Bind Authorization.
- Bind Authorization is not Bind Invocation.

The local Ed25519 verifier accepts public keys only from deployment-controlled
configuration. Public keys and `verified`, `signature_verified`, `not_revoked`,
or similar flags supplied in an artifact never establish trust. Production
KMS/HSM and prefetched revocation services can implement the verifier/checker
protocols without changing the runtime trust boundary.
