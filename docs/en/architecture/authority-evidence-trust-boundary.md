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

`VerifiedAuthorityEvidence` records cryptographic, verifier-derived proof; the
object alone is not deployment-authorized production authority. Production
acceptance additionally requires the deployment-controlled authority verifier
policy, revocation policy, and a successful `RuntimeAuthorityValidator` result.

Deployment configuration owns both trusted signing keys and the verifier
allowlist. The verifier policy binds verifier identity, trust level, verifier
key and policy identity, and the independently approved signer-policy hash.
Artifact-supplied keys or self-asserted `production` labels cannot bootstrap
trust. Revocation status must come from an allowed source and must be
timezone-aware, non-future, and no older than the configured maximum age.

Core governance defines protocols and proof models without importing an
optional cryptography package. The concrete Ed25519 implementation lives in
`authority_evidence_signing` and is imported explicitly only by deployments
that install the signing extra. All signed artifacts bind artifact type,
version, claims hash, and `signed_at` in one canonical domain-separated payload.

For compatibility, an absent `action_contract_hash` is omitted from legacy
content identity. A supplied hash is included, and strict proof verification
requires it to equal the exact action-contract digest. All strict-path times
must carry a UTC offset; naive timestamps fail closed.

These guarantees are deliberately separate:

- Hash matches does not imply authentic authority.
- A valid signature does not imply an authorized signer.
- An authorized signer does not imply current non-revocation.
- `VerifiedAuthorityEvidence` is not Human Approval.
- `VerifiedAuthorityEvidence` is not Bind Authorization.
- Bind Authorization is not Bind Invocation.
- Bind Invocation is not successful execution.

The local Ed25519 verifier accepts public keys only from deployment-controlled
configuration. Public keys and `verified`, `signature_verified`, `not_revoked`,
or similar flags supplied in an artifact never establish trust. Production
KMS/HSM and prefetched revocation services can implement the verifier/checker
protocols without changing the runtime trust boundary.
