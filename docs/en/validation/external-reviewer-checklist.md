# External Reviewer Checklist

Use this checklist to evaluate what is implemented today without over-reading roadmap claims.

## A. Reading order (fast path)

- [ ] Read [Short DD Summary](short-dd-summary.md).
- [ ] Read [Implemented vs Pending Boundary](implemented-vs-pending-boundary.md).
- [ ] Read [Governance Capability Matrix](governance-capability-matrix.md).

## B. Contract and governance checks

- [ ] Confirm canonical decision semantics and forbidden combinations are explicitly documented.
- [ ] Confirm required evidence taxonomy and AML/KYC profile behavior are explicitly documented.
- [ ] Confirm governance backend choices and operational constraints are documented.

Primary docs:
- `docs/en/architecture/decision-semantics.md`
- `docs/en/governance/required-evidence-taxonomy.md`
- `docs/en/operations/postgresql-production-guide.md`

## C. Validation and evidence checks

- [ ] Confirm production validation strategy and boundaries are documented.
- [ ] Confirm external audit readiness includes verifier and bundle pathway.
- [ ] Confirm evidence bundle acceptance checklist is part of handoff contract.

Primary docs:
- `docs/en/validation/production-validation.md`
- `docs/en/validation/backend-parity-coverage.md`
- `docs/en/validation/external-audit-readiness.md`

## D. AML/KYC pilot proof checks

- [ ] Confirm pilot package is scoped to synthetic cases.
- [ ] Confirm strict required-evidence pilot mode path exists.
- [ ] Confirm expected-case and failure-case fixtures are present.

Primary docs/data:
- `docs/en/guides/poc-pack-financial-quickstart.md`
- `docs/en/guides/aml-kyc-pilot-checklist.md`
- `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`

## E. Boundary / anti-exaggeration checks

- [ ] Ensure no claim of completed third-party certification unless evidence is attached.
- [ ] Ensure no claim of universal production certification.
- [ ] Ensure pending items are explicitly separated from implemented behavior.

Use:
- `docs/en/validation/implemented-vs-pending-boundary.md`

