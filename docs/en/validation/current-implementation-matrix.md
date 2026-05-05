# Current Implementation Matrix

## Purpose

This document separates implemented facts from PoC scope, roadmap direction,
and non-certification boundaries for external reviewers.

## Reading rules

- This document is not legal advice.
- This document is not regulatory approval.
- This document is not third-party certification.
- "Implemented" means implemented in this repository, not necessarily
  production-validated in a customer environment.
- "PoC" means deterministic or fixture-backed proof path unless explicitly
  connected to a live external system.

## Matrix

| Claim / Capability | Current implementation | Main endpoint / file / artifact | Test or validation evidence | Current limitation | Status |
| --- | --- | --- | --- | --- | --- |
| Core decision pipeline | `/v1/decide` is implemented with governance and audit-facing lineage semantics, including FUJI gate and TrustLog-linked artifacts. Replay/audit pathways are documented for operator review flows. | `POST /v1/decide`; `docs/en/architecture/decision-semantics.md`; `docs/en/validation/pre-bind-formation-refusal-mini-proof.md` | `/v1/decide` pre-bind mini proof and canonical proof docs; Mission Control → Audit workflow demo checks | Documentation and focused proofs do not alone prove every production customer context. | Implemented |
| Bind-boundary governance | `decision -> execution_intent -> bind_receipt` lineage is documented; `bind_summary` + `bind_receipt` vocabulary is exposed for bind-governed mutation/export responses. | `docs/en/architecture/bind-boundary-governance-artifacts.md`; `GET /v1/governance/bind-receipts/{bind_receipt_id}` | `docs/en/guides/aml-kyc-operator-runbook.md`; `docs/en/guides/governance-policy-bundle-promotion.md` | Not all effect-bearing routes are guaranteed bind-governed unless covered in bind coverage docs and tests. | Implemented / Partial |
| Operator-governed effect paths (minimum documented set) | Five operator mutation paths are explicitly documented as bind-governed: `PUT /v1/governance/policy`, `POST /v1/governance/policy-bundles/promote`, `PUT /v1/compliance/config`, `POST /v1/system/halt`, `POST /v1/system/resume`. | `README.md`; `docs/en/guides/governance-policy-bundle-promotion.md` | README implementation fact section; governance promotion guide and operator runbook | Coverage is explicit for selected paths; broader route coverage depends on bind coverage registry/test scope. | Implemented / Partial |
| Regulated Action Governance Kernel | Action Class Contract, Authority Evidence, Runtime Authority Validation, Admissibility Predicate, and Commit Boundary Evaluator are documented as implemented kernel components. Regulated-action fields are documented in bind artifacts/proof pack paths. | `docs/en/architecture/regulated-action-governance-kernel.md`; `docs/en/architecture/authority-evidence-vs-audit-log.md`; `docs/en/validation/regulated-action-governance-proof-pack.md` | Regulated Action Governance proof pack + quality gate + external handoff docs | External authority feeds, real bank/sanctions/compliance integrations, and third-party completed review are not represented as fully completed in-repo facts. | Implemented / Partial |
| AML/KYC beachhead PoC | Deterministic fixture-backed AML/KYC escalation path is packaged as executable PoC flow. | `scripts/run_aml_kyc_poc_fixture.py`; `veritas_os/sample_data/governance/aml_kyc_poc_pack/`; `docs/en/guides/poc-pack-financial-quickstart.md` | PoC quickstart, operator runbook, pilot checklist, success criteria | Fixture-based PoC evidence is not equal to live bank-side production integration. | Implemented / PoC |
| Mission Control / Governance UI | Mission Control includes live governance snapshot, governance artifact panel, and safe internal audit link flow; bind cockpit / audit operator surfaces are documented. | `GET /v1/governance/live-snapshot`; `README.md` Mission Control flow section; frontend audit docs/tests referenced in README | `scripts/demo_mission_audit_workflow.sh`; focused Mission Control/Audit checks listed in README | Enterprise UX validation and production operator workflow validation across customer environments remain future work. | Implemented / Partial |
| PostgreSQL production path | Repository documentation states PostgreSQL as formal production path for MemoryOS and TrustLog, with Docker Compose defaulting to PostgreSQL. Migration and validation docs exist. | `README.md` PostgreSQL sections; `docs/en/operations/postgresql-production-guide.md`; `docs/en/operations/database-migrations.md`; `docs/en/validation/postgresql-production-proof-map.md` | Backend parity coverage, production validation docs, live PostgreSQL validation entrypoints | HA/DR posture and managed-cloud operations guarantees depend on environment-specific deployment and controls. | Implemented / Partial |
| Runtime posture and security controls | `VERITAS_POSTURE` model (dev/staging/secure/prod) and posture-derived fail-closed defaults are documented, including secret manager, transparency, WORM, replay strictness controls. | `README.md` runtime posture section; `docs/en/operations/security-hardening.md` | Security and posture docs; quality/release documentation | Actual guarantees depend on deployed environment configuration, secrets, and operations discipline. | Prepared / Not certified |
| Governance artifact identity / signing | Policy/governance identity fields such as `policy_version`, `digest`, `signature_verified`, `signer_id`, and `verified_at` are documented in decision/governance flows. | `README.md`; `docs/en/operations/governance-artifact-signing.md`; governance architecture docs | Signing runbook + governance docs + quality gate artifacts | Production-grade key custody depends on configured KMS/HSM or equivalent backend posture. | Implemented / Partial |
| CI / Release Gate / validation evidence | CI, CodeQL, Release Gate, Docker/GHCR-related release evidence and production validation workflows are documented with layered test/validation model. | `.github/workflows/`; `README.md` CI section; `docs/en/validation/production-validation.md`; `docs/en/validation/release-gate-recovery-case-study.md` | Tiered validation docs + release gate recovery case study + validation packs | Focused validation evidence must not be interpreted as blanket proof that every test class always passes in all contexts. | Implemented / Partial |
| Third-party review readiness | Technical proof pack, external review handoff pack, and external reviewer feedback template are provided for reviewer workflows. | `docs/en/validation/technical-proof-pack.md`; `docs/en/validation/external-review-handoff-regulated-action-governance.md`; `docs/en/validation/external-reviewer-feedback-template-regulated-action-governance.md` | Third-party readiness and external audit readiness documents | Prepared for review handoff; not equivalent to completed third-party certification. | Prepared / Not certified |
| Documentation and positioning | README, README_JP, positioning docs, and proof packs are extensive and linked for public/external consumption. | `README.md`; `README_JP.md`; `docs/en/positioning/public-positioning.md` | Documentation hub/index and validation packs | Documentation breadth can increase onboarding time without guided reviewer path. | Implemented / Partial |
| Roadmap / not yet integrated areas | External authority source integration, real bank/sanctions/compliance system integration, broader regulated action class coverage, third-party completed review, production customer workflow validation, deeper enterprise IdP/JWT scope models are positioned as ongoing/future work. | `README.md` roadmap/limits sections; review/readiness docs | Roadmap and limitation statements across README and validation docs | These are intentionally outside current fully proven repository scope. | Roadmap |

## Current strongest evidence

- Bind-boundary lineage (`decision -> execution_intent -> bind_receipt`) is documented and reflected in operator workflows.
- Selected operator-governed effect paths are explicitly documented with bind-governed expectations.
- Regulated Action Governance kernel artifacts and evaluation semantics are documented with proof and quality-gate packs.
- AML/KYC deterministic fixture-backed PoC path is executable via script + sample data + quickstart.
- Mission Control and Audit operator surfaces include safe audit link traversal and bind artifact flow documentation.
- PostgreSQL production path is documented with parity, migration, and validation evidence entrypoints.
- Posture-based fail-closed runtime controls are documented with secure/prod expectations.
- Quality-gate, external audit readiness, and reviewer handoff packs are available.

## Current limits

- This is not full production certification.
- This is not legal or regulatory approval.
- Not all real-world external integrations are completed in-repo.
- Not all effect-bearing paths are guaranteed bind-governed unless explicitly covered.
- Enterprise deployment still requires environment-specific hardening and operations.
- Third-party completed audit/review remains pending.
- Full test/type-check status should be treated as verified only where CI evidence is explicit.

## Recommended reviewer path

1. `README.md`
2. `docs/REVIEWER_ENTRYPOINT.md`
3. `docs/en/validation/current-implementation-matrix.md`
4. `docs/en/development/recent-hardening.md`
5. `docs/en/validation/regulated-action-governance-proof-pack.md`
6. `docs/en/guides/poc-pack-financial-quickstart.md`
7. `docs/en/validation/external-review-handoff-regulated-action-governance.md`
