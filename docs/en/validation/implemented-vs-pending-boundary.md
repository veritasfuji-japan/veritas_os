# Implemented vs Pending Boundary (External Proof Scope)

**Intent:** Keep boundary statements short, explicit, and verifiable.

## Implemented (repository-verifiable)

1. Decision semantics contract and runtime-enforcement path are defined.
2. Required evidence taxonomy v0 + AML/KYC profile logic is defined.
3. Governance backend repository abstraction (file/postgresql) is implemented.
4. Evidence bundle generation and standalone TrustLog verification paths are implemented.
5. Validation strategy docs and pilot checklists are present for reproducible review flow.

## Pending / environment-dependent

1. Independent third-party certification/audit completion.
2. Tenant-specific production controls (IdP, key custody, HA/DR topology, legal retention policy execution).
3. Customer environment legal/compliance acceptance of bundle formats and procedures.
4. Full production-readiness guarantee for every deployment context.

## Not yet guaranteed (must read)

- No claim of universal production certification.
- No claim that self-assessment equals external certification.
- No claim that synthetic AML/KYC pilots are legal determinations.
- No claim that provider/integration controls not in this repository are already implemented.

## Evidence pointers

- [Public Positioning (self-assessment boundary)](../positioning/public-positioning.md)
- [Decision Semantics Contract](../architecture/decision-semantics.md)
- [Required Evidence Taxonomy](../governance/required-evidence-taxonomy.md)
- [External Audit Readiness](external-audit-readiness.md)
- [AML/KYC Pilot Checklist](../guides/aml-kyc-pilot-checklist.md)

