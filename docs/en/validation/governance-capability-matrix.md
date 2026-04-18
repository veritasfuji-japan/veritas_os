# Governance Capability Matrix (Implemented vs Pending)

**Snapshot date:** 2026-04-18 (UTC)

This matrix is intentionally conservative. "Implemented" means repository-visible behavior exists today. "Pending" means external proof, operational rollout depth, or formal certification is still required.

| Capability area | Current status | Repository evidence | Pending / boundary |
|---|---|---|---|
| Decision semantics contract | Implemented | Canonical gate semantics + combination rules documented and mapped to runtime enforcement paths | External integrator conformance certification is pending |
| Gate/business consistency enforcement | Implemented | Forbidden combinations and canonicalization behavior are documented as runtime-enforced | Independent third-party protocol conformance review is pending |
| Required evidence taxonomy | Implemented (v0 + AML/KYC profile) | Taxonomy and profile/mode behavior documented (`warn`/`strict`) | Domain expansion and hard-reject migration policy are pending |
| Governance backend abstraction | Implemented | Governance backends documented and file/postgresql repository path exists in code and tests | Enterprise-managed DB topology certification is environment-dependent |
| TrustLog verification path | Implemented | Standalone verifier path and evidence verification flow documented | External custody/retention legal acceptance depends on customer controls |
| Evidence bundle generation | Implemented | Bundle schema/content/acceptance checklist documented | Customer-specific evidentiary admissibility review pending |
| AML/KYC pilot package | Implemented for synthetic pilot scope | Pilot checklist/runbook/fixture and evidence handoff docs available | Real customer data deployment and legal sign-off are pending |
| Governance control-plane operations | Implemented baseline | Governance artifact lifecycle + signing/operations docs exist | Full organizational SoD/change-approval evidence depends on tenant setup |
| Production posture guarantees | Partially implemented (bounded) | Production validation and hardening docs define controls and limits | Universal HA/DR and cloud posture guarantees are not asserted |

## Notes for external reviewers

- Treat this matrix as a navigation/claim-boundary layer, not a certification statement.
- When in doubt, request artifact-level proof via the reviewer checklist.

## Core references

- [Decision Semantics Contract](../architecture/decision-semantics.md)
- [Required Evidence Taxonomy](../governance/required-evidence-taxonomy.md)
- [External Audit Readiness](external-audit-readiness.md)
- [Production Validation](production-validation.md)
- [PostgreSQL Production Guide](../operations/postgresql-production-guide.md)

