# Documentation (English)

This directory is the English documentation entrypoint.
VERITAS OS is a **Decision Governance and Bind-Boundary Control Plane for AI Agents**.

For the universal bilingual index, see [../INDEX.md](../INDEX.md).
For the bilingual correspondence table, see [../DOCUMENTATION_MAP.md](../DOCUMENTATION_MAP.md).

日本語版: [../ja/README.md](../ja/README.md)

---

## Sections

### AML/KYC Beachhead (role-based fastest routes)
- **Customer (business owner / compliance lead)**:
  [AML/KYC short positioning](positioning/aml-kyc-beachhead-short-positioning.md)
- **Operator (implementation / governance owner)**:
  [1-day PoC quickstart + operator guide](guides/poc-pack-financial-quickstart.md)
- **Investor / board observer**:
  [Investor-facing short explanation](positioning/aml-kyc-beachhead-short-positioning.md)
- **Evidence bundle readiness**:
  [External audit readiness](validation/external-audit-readiness.md)

### Operations & Runbooks
- [PostgreSQL Production Guide](operations/postgresql-production-guide.md)
- [PostgreSQL Drill Runbook](operations/postgresql-drill-runbook.md)
- [Security Hardening Checklist](operations/security-hardening.md)
- [Database Migrations (Alembic)](operations/database-migrations.md)
- [Operational Readiness Runbook](operations/operational-readiness-runbook.md)
- [Release Process](operations/release-process.md)
- [Environment Variable Reference](operations/env-reference.md)
- [Dependency Profiles](operations/dependency-profiles.md)
- [Legacy Path Cleanup](operations/legacy-path-cleanup.md)
- [Governance Artifact Signing](operations/governance-artifact-signing.md)
- [Memory Pickle Migration](operations/memory_pickle_migration.md)
- [TrustLog Observability](operations/trustlog_observability.md)

### Validation & Testing
- [Production Validation Strategy](validation/production-validation.md)
- [Backend Parity Coverage](validation/backend-parity-coverage.md)
- [External Audit Readiness](validation/external-audit-readiness.md)
- [Technical Proof Pack (external review)](validation/technical-proof-pack.md)

### Governance & Compliance
- [Decision Semantics Contract](architecture/decision-semantics.md)
- [Bind-Boundary Governance Artifacts](architecture/bind-boundary-governance-artifacts.md)
- [Bind-Time Admissibility Evaluator](architecture/bind_time_admissibility_evaluator.md)
- [Required Evidence Taxonomy v0](governance/required-evidence-taxonomy.md)
- [Governance Artifact Lifecycle](governance/governance-artifact-lifecycle.md)

### Guides
- [3-Minute Demo Script](guides/demo-script.md)
- [Financial PoC Pack (1-day quickstart, EN)](guides/poc-pack-financial-quickstart.md)
- [Financial PoC Success Criteria](guides/financial-poc-success-criteria.md)
- [Operator Guide: Policy Bundle Promotion](guides/governance-policy-bundle-promotion.md)
- [File-to-PostgreSQL Migration Guide](guides/migration-guide.md) (bilingual)
- [Financial PoC Pack (1-day quickstart, JA)](../ja/guides/poc-pack-financial-quickstart.md)

### Reviews
- [Reviews Index](reviews/README.md)

### Notes
- [Chainlit Integration](notes/chainlit.md)

### Architecture (shared)
- [Architecture Docs](../architecture/) (continuation runtime, core boundaries, TrustLog)

### EU AI Act (shared)
- [EU AI Act Compliance](../eu_ai_act/) (risk assessment, model card, bias, DPA)

### UI / Frontend (shared)
- [UI Docs](../ui/) (architecture, integration plan, preview)

### Benchmarks (shared)
- [Evidence Benchmark Plan](../benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md)
