# Press Release Summary: Governance Artifacts as Signed Control-Plane Assets

## Problem

Governance artifacts were historically treated as deploy-time options, which made
provenance and authenticity harder to prove during production audits.

## Trust model

VERITAS OS now treats governance bundles as control-plane assets that require:

- cryptographic signature verification,
- attributable approvals,
- digest-linked change history,
- decision-time identity threading (`governance_identity`).

## Posture differences

- `dev` / `staging`: support practical migration by allowing unsigned/legacy bundles with warnings.
- `secure` / `prod`: fail-closed; reject unsigned, invalid, or SHA-256-only governance artifacts.

## Migration challenge

Main migration work is converting existing unsigned artifacts and rollout workflows
into Ed25519-signed bundles while maintaining release velocity.

## Residual risks

- Key custody/operational mistakes can still block rollout.
- Signer metadata quality (`key_id` hygiene) remains an operator responsibility.
- Non-strict postures can still run with warnings if teams do not enforce promotion gates.

## Governance artifact lifecycle (short note)

Author → Approve (4-eyes) → Sign (Ed25519) → Verify (posture-aware) → Activate
→ Thread into decisions (`policy_version`, `digest`, `signature_verified`, `signer_id`)
→ Audit digest transitions (`previous_digest` → `new_digest`) → Governed rollback.
