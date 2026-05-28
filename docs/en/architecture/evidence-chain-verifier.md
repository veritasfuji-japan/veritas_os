# Evidence Chain Verifier v1

Evidence Chain Verifier v1 is a deterministic local/offline verifier for
`EvidenceChainManifest` artifacts.

It answers a narrow question:

> Does this `EvidenceChainManifest` match the supplied governance artifacts it
> claims to reference?

## What it verifies

The verifier compares a manifest with supplied local/offline artifacts by:

- recomputing `manifest.deterministic_digest()` and comparing it with
  `manifest.manifest_hash`;
- recomputing artifact hashes through `deterministic_digest()` when available;
- reading deterministic hash fields such as `evidence_hash`, `receipt_hash`,
  `outcome_hash`, `manifest_hash`, or `bind_receipt_hash` when a digest method
  is not available;
- checking claimed bind coverage operation metadata against the supplied
  operation id; and
- reporting verified, missing, mismatched, or indeterminate links.

For v1, the verifier is intentionally small and additive. It complements
Evidence Chain Manifest v1 by checking whether the manifest's claimed links match
available local artifacts, rather than only validating the manifest shape.

## Result statuses

`EvidenceChainVerificationResult` uses deterministic statuses:

- `verified` — the manifest exists, the manifest hash matches, every claimed
  supplied link verifies, and no failure reason is present.
- `failed` — a manifest hash or artifact hash mismatch is detected, or verifier
  timestamp validation fails.
- `incomplete` — a manifest claims a link but the required artifact or coverage
  operation id was not supplied.
- `indeterminate` — an artifact was supplied, but the verifier cannot determine
  a deterministic hash for it and no direct mismatch is proven.

The verifier preserves the manifest's own `missing_links` information for
blocked or incomplete chains. Missing links recorded by the manifest itself are
not treated as tampering unless the manifest claims a hash and the corresponding
artifact is absent, mismatched, or indeterminate.

## Local/offline boundary

Evidence Chain Verifier v1 does **not** connect to live SaaS, IdP, IAM, SSO,
bank, sanctions, customer systems, production approval systems, or live audit
stores. It performs no live network calls, requires no credentials, and does not
introduce production execution behavior.

This verifier is not legal advice, regulatory approval, third-party
certification, production audit certification, or proof of live production audit
coverage. It is a deterministic local/offline consistency checker for governance
artifacts supplied to it.
