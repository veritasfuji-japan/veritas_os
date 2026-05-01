# VERITAS OS v2.0 — Decision Governance and Bind-Boundary Control Plane for AI Agents

**Reviewable, traceable, replayable, auditable, and enforceable AI decisions through decision and bind boundaries before real-world effect.**

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.17838349-0E76A8?logo=doi&logoColor=white)](https://doi.org/10.5281/zenodo.17838349)
[![DOI (JP Paper)](https://img.shields.io/badge/DOI%20(JP)-10.5281%2Fzenodo.17838456-0E76A8?logo=doi&logoColor=white)](https://doi.org/10.5281/zenodo.17838456)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Next.js](https://img.shields.io/badge/Next.js-16-black)
![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![CodeQL](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml)
[![Release Gate](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
![Coverage](https://img.shields.io/badge/coverage-87%25-brightgreen)
![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-blue)
[![README JP](https://img.shields.io/badge/README-日本語-0f766e.svg)](README_JP.md)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Takeshi%20Fujishita-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/takeshi-fujishita-279709392?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

VERITAS OS is a **Decision Governance and Bind-Boundary Control Plane** for AI agents.
Instead of passing model output directly to execution, VERITAS routes each decision through a **reproducible, fail-closed, safety-gated, hash-chained governance pipeline** with an operator-facing governance surface in **Mission Control** and governance APIs.

This project is not only about running agents.
It is about making AI decisions **reviewable, traceable, replayable, auditable, and enforceable** inside real organizational workflows before they have real-world effect, with bind artifacts exposed as full bind receipts and compact bind summaries.

> **Mental model:** LLM = CPU, VERITAS OS = Decision / Agent Governance OS on top

## Governance Review Workflow

VERITAS OS does not only record governance artifacts. It connects them into a Mission Control → Audit review workflow:

```mermaid
flowchart LR
  A[Mission Control<br/>Live governance snapshot] --> B[Governance artifacts panel<br/>pre-bind source / bind reason / target metadata / check results]
  B --> C[Safe operator actions<br/>internal /audit?... links]
  C --> D[Audit<br/>query validation]
  D --> E{Supported artifact}
  E -->|decision_id| F[Auto-load latest logs<br/>focus matching timeline item]
  E -->|bind_receipt_id| G[Dedicated bind receipt lookup<br/>fallback detail]
  E -->|execution_intent_id| I[Auto-load latest logs<br/>timeline focus or unavailable]
  E -->|invalid or unsafe| H[Reject<br/>no fake route]
```


1. Mission Control receives a live governance snapshot from `/v1/governance/live-snapshot`.
2. The UI surfaces governance artifact metadata, including pre-bind source, bind reason, target metadata, check results, and safe operator actions.
3. Operator actions provide safe internal `/audit?...` links for supported artifacts (`bind_receipt_id`, `decision_id`, `execution_intent_id`).
4. Audit consumes supported query parameters and applies query validation before lookup/navigation.
5. Decision traces auto-load latest logs and focus matching timeline artifacts when available, with direct lookup fallback when timeline data does not contain the decision.
6. Bind receipt traces use dedicated lookup and render fallback detail when timeline items do not contain the target receipt.
7. Unsafe links, external/protocol URLs, malformed hrefs, and fake routes are not generated.

Local workflow check:

`bash scripts/demo_mission_audit_workflow.sh`

A successful run should complete the focused checks for Mission Control actions, Audit page tracing, Audit hook behavior, and safe link validation:

```text
Running VERITAS Mission Control → Audit workflow demo checks...
✓ Mission Control artifact actions
✓ Audit page decision / bind receipt tracing
✓ Audit hook query workflow
✓ Governance link safety validation
Mission Control → Audit workflow demo checks completed.
```

Covered by focused frontend tests:

- `frontend/components/mission-page.test.tsx`
- `frontend/app/audit/page.test.tsx`
- `frontend/app/audit/hooks/useAuditData.test.ts`
- `frontend/lib/governance-link-utils.test.ts`

See `docs/ui/README_UI.md` for implementation details.

## Version

- **Version:** 2.0.0
- **Release Status:** Beta
- **Author:** Takeshi Fujishita

## What VERITAS OS is

VERITAS OS is a **Decision Governance and Bind-Boundary Control Plane for AI Agents**.
It is the governance layer from **decision adjudication through bind-time boundary checks**:
it determines whether an AI decision may proceed and whether an approved decision
can be committed, blocked, escalated, rolled back, or fail safely at bind time before
real-world effect.
It now also exposes an additive pre-bind schema surface for participation
admissibility signals without changing the existing bind-time commitment contract.

### What problem it solves

In enterprise and regulated environments, the key failure mode is often not model intelligence but **uncontrolled execution**.
VERITAS addresses this by making decisions:

- **Reviewable** before action
- **Traceable** to evidence and policy context
- **Replayable** with divergence awareness
- **Auditable** through tamper-evident artifacts
- **Enforceable** through fail-closed policy and safety gates

### Why bind-boundary control matters

Decision approval alone is not commitment.
VERITAS keeps this boundary explicit by carrying governance lineage from decision adjudication into bind-time control,
so operators can verify whether an approved decision was committed, blocked, escalated, rolled back, or failed safely before real-world effect.

### How it differs from runtime/orchestration tools

Many agent stacks optimize task execution and tool wiring.
VERITAS OS focuses on **decision governance and bind-boundary control**:

- Governance controls are applied **before real-world effect**.
- FUJI gate behavior is **fail-closed by default** on unsafe/undefined paths.
- TrustLog + governance identity create **audit-grade decision lineage**.
- Mission Control + governance APIs provide an operator-facing governance surface with bind-phase outcomes, bind receipts, and compact bind summaries, not only developer telemetry.
- `/v1/decide` now follows a shared operator-facing contract pattern: `*_operator_summary` is minimal-by-default, while `*_operator_detail` is only emitted when `operator_verbosity=expanded` and role policy permits.

### Why this fits regulated / enterprise use

- Explicit approval boundaries and policy enforcement points
- Evidence capture and replay pathways for post-incident review
- Signed and hash-linked governance artifacts for accountability
- Posture-based secure/prod startup checks to reduce permissive misconfiguration

This opening reflects current implemented fact: bind-governed adjudication is already active on at least five operator-governed effect paths,
while broader effect-path coverage remains roadmap direction.

VERITAS OS includes a Regulated Action Governance Kernel for selected AI-agent action paths. It uses Action Class Contracts, Authority Evidence, Runtime Authority Validation, Admissibility Predicates, and Irreversible Commit Boundary checks to determine whether an execution intent should commit, block, escalate, or refuse at the bind boundary, including an AML/KYC customer risk escalation fixture path.

Audit Log records what happened. Authority Evidence records why an action was authorized and admissible at bind time; audit log records alone do not authorize commit.

This is not legal advice, not regulatory approval, not third-party certification, or a claim of compliance by itself.

External reviewers can start from the Regulated Action Governance External Review Handoff Pack, which links the implemented AML/KYC action path, evidence artifacts, quality gate, and known limitations.
External reviewers can use the Regulated Action Governance External Reviewer Feedback Template to record review scope, assessment criteria, findings, evidence requests, and recommendations.

## What VERITAS OS is / is not

- **Is:** a Decision Governance and Bind-Boundary Control Plane for AI agents, covering decision governance and bind-boundary governance before real-world effect.
- **Is not:** a replacement for all agent runtimes, nor only an orchestration convenience wrapper.

## Fact vs roadmap (read this first)

- **Current fact (beta):** Core decision pipeline, bind artifact lineage (`decision -> execution_intent -> bind_receipt`), bind-time admissibility checks, FUJI fail-closed gating, TrustLog lineage, Mission Control workflows, and governance endpoints are implemented.
- **Current fact (bind policy surface):** Bind-boundary adjudication is currently wired on at least five operator-governed effect paths:
  1) `PUT /v1/governance/policy` (governance policy update path),
  2) `POST /v1/governance/policy-bundles/promote` (policy bundle promotion path), and
  3) `PUT /v1/compliance/config` (runtime compliance config mutation path), and
  4) `POST /v1/system/halt` (operator emergency halt mutation path), and
  5) `POST /v1/system/resume` (operator system resume mutation path).
- **Current fact (bind outcome public contract):** Governance bind responses expose legacy flat bind fields (`bind_outcome`, `bind_failure_reason`, `bind_reason_code`, `execution_intent_id`, `bind_receipt_id`) and additive `bind_summary` objects as a shared compact bind vocabulary.
- **Current fact (bind coverage registry):** VERITAS maintains a tested bind coverage registry for API effect paths. Effect-bearing routes must be classified as `bind_governed` or explicitly documented as `audited_exemption` with reason/risk metadata, reducing the risk that recorded decisions are treated as execution permission without a binding artifact.
- **Current fact (bind artifact family):** `BindReceipt` is persisted as a full governance artifact and carries canonical target metadata as part of the artifact contract.
- **Current fact (pre-bind participation schema):** `/v1/decide` supports an optional additive `participation_signal` object as an upstream signal family (`participation_signal -> decision -> execution_intent -> bind_receipt`) for participation admissibility; bind-time commitment admissibility remains unchanged.
- **Current fact (pre-bind structural detection):** `/v1/decide` can emit optional additive `pre_bind_detection_summary` / `pre_bind_detection_detail` fields that classify structural participation state (`informative|participatory|decision_shaping`) from the participation signal family; this is upstream-only and does not change bind-time governance.
- **Current fact (pre-bind preservation layer):** `/v1/decide` can emit optional additive `pre_bind_preservation_summary` / `pre_bind_preservation_detail` fields that classify governability-preservation state (`open|degrading|collapsed`) and intervention viability; this is distinct from detection and does not replace bind-time governance.
- **Current fact (OpenAPI parity):** `openapi.yaml` now explicitly declares the additive `/v1/decide` pre-bind surfaces (`participation_signal`, `pre_bind_detection_summary/detail`, `pre_bind_preservation_summary/detail`) as optional fields, aligned with runtime and architecture vocabulary.
- **Current fact (replay/operator flow):** Operator surfaces expose bind artifacts via list/export/detail endpoints (`/v1/governance/bind-receipts`, `/v1/governance/bind-receipts/export`, `/v1/governance/bind-receipts/{bind_receipt_id}`), with mutation/export responses reusing `bind_summary` for triage and audit workflows.
- **Current fact (boundary):** Production readiness still depends on environment-specific hardening, integration, and operational controls.
- **Roadmap / future direction:** Bind-boundary policy surface is expected to expand to more effect paths and become a broader standardization framework for multi-path effect governance; this is direction, not a claim of full completion today.
- **Roadmap:** Expanded enterprise integrations (for example deeper IdP/JWT scope models and broader distributed failure-mode validation).

### Regulated action governance fact (implemented)

- Action Class Contract
- AML/KYC Customer Risk Escalation contract
- Authority Evidence artifact
- Runtime Authority Validation
- Admissibility Predicate evaluation
- Commit Boundary Evaluator
- BindReceipt / BindSummary regulated-action fields
- AML/KYC deterministic regulated action path
- Mission Control / Bind Cockpit regulated action display
- Proof Pack / Quality Gate docs

### Regulated action governance roadmap (not yet implemented)

- Real external authority source integration
- Real bank / sanctions / compliance system integration
- Third-party review
- Broader regulated action-class coverage
- Production customer workflow validation

### Technical Maturity Snapshot (internal)

> This is a **self-assessment / internal re-evaluation** summary (not third-party certification), published as a conservative internal snapshot.

- Latest internal re-evaluation date: **2026-04-15**
- Internal overall snapshot: **85 / 100** (from 82 on 2026-03-15)
- Full internal table, change log, and residual risks: [`docs/en/positioning/public-positioning.md`](docs/en/positioning/public-positioning.md)

---

## Quick Links

- **AML/KYC Beachhead (1-day PoC quickstart)**: [`docs/en/guides/poc-pack-financial-quickstart.md`](docs/en/guides/poc-pack-financial-quickstart.md)
- **AML/KYC Governance Template Contract**: [`docs/en/guides/financial-governance-templates.md`](docs/en/guides/financial-governance-templates.md)
- **External Audit / Evidence Bundle Readiness**: [`docs/en/validation/external-audit-readiness.md`](docs/en/validation/external-audit-readiness.md)
- **External Technical Proof Pack (review/pilot/DD/audit)**: [`docs/en/validation/technical-proof-pack.md`](docs/en/validation/technical-proof-pack.md)
- **Third-Party Review Readiness (compact index)**: [`docs/en/validation/third-party-review-readiness.md`](docs/en/validation/third-party-review-readiness.md)
- **AML/KYC Short Positioning (customer / operator / investor)**: [`docs/en/positioning/aml-kyc-beachhead-short-positioning.md`](docs/en/positioning/aml-kyc-beachhead-short-positioning.md)
- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo paper (EN)**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo paper (JP)**: https://doi.org/10.5281/zenodo.17838456
- **Japanese README**: [`README_JP.md`](README_JP.md)
- **User Manual (JP)**: [`docs/ja/guides/user-manual.md`](docs/ja/guides/user-manual.md)
- **Contributing**: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Security Policy**: [`SECURITY.md`](SECURITY.md)
- **Documentation Index**: [`docs/INDEX.md`](docs/INDEX.md)
- **PostgreSQL Production Guide**: [`docs/en/operations/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md)
- **PostgreSQL Drill Runbook**: [`docs/en/operations/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md)
- **Security Hardening**: [`docs/en/operations/security-hardening.md`](docs/en/operations/security-hardening.md)
- **Database Migrations**: [`docs/en/operations/database-migrations.md`](docs/en/operations/database-migrations.md)
- **Backend Parity Coverage**: [`docs/en/validation/backend-parity-coverage.md`](docs/en/validation/backend-parity-coverage.md)
- **PostgreSQL Production Proof Map (compact)**: [`docs/en/validation/postgresql-production-proof-map.md`](docs/en/validation/postgresql-production-proof-map.md)
- **Live PostgreSQL Validation Evidence**: [`docs/live-postgresql-validation.md`](docs/live-postgresql-validation.md)
- **Legacy Path Cleanup**: [`docs/en/operations/legacy-path-cleanup.md`](docs/en/operations/legacy-path-cleanup.md)
- **Review Document Map**: [`docs/ja/reviews/code-review-document-map.md`](docs/ja/reviews/code-review-document-map.md)
- **Documentation Hub (EN)**: [`docs/en/README.md`](docs/en/README.md)
- **Documentation Hub (JA)**: [`docs/ja/README.md`](docs/ja/README.md)
- **Public Positioning Guide (EN)**: [`docs/en/positioning/public-positioning.md`](docs/en/positioning/public-positioning.md)
- **Public Positioning Guide (JA)**: [`docs/ja/positioning/public-positioning.md`](docs/ja/positioning/public-positioning.md)
- **Decision Semantics Contract**: [`docs/en/architecture/decision-semantics.md`](docs/en/architecture/decision-semantics.md)
- **Bind-Boundary Governance Artifacts**: [`docs/en/architecture/bind-boundary-governance-artifacts.md`](docs/en/architecture/bind-boundary-governance-artifacts.md)
- **Bind-Time Admissibility Evaluator**: [`docs/en/architecture/bind_time_admissibility_evaluator.md`](docs/en/architecture/bind_time_admissibility_evaluator.md)
- **Pre-Bind Participation Signals**: [`docs/en/architecture/pre-bind-participation-signals.md`](docs/en/architecture/pre-bind-participation-signals.md)
- **Pre-Bind Canonical Proof Cases**: [`docs/en/proofs/pre_bind_canonical_cases_proof.md`](docs/en/proofs/pre_bind_canonical_cases_proof.md)
- **Regulated Action Governance Kernel**: [`docs/en/architecture/regulated-action-governance-kernel.md`](docs/en/architecture/regulated-action-governance-kernel.md)
- **Authority Evidence vs Audit Log**: [`docs/en/architecture/authority-evidence-vs-audit-log.md`](docs/en/architecture/authority-evidence-vs-audit-log.md)
- **AML/KYC Regulated Action Path (Use Case)**: [`docs/en/use-cases/aml-kyc-regulated-action-path.md`](docs/en/use-cases/aml-kyc-regulated-action-path.md)
- **Regulated Action Governance Proof Pack**: [`docs/en/validation/regulated-action-governance-proof-pack.md`](docs/en/validation/regulated-action-governance-proof-pack.md)
- **Regulated Action Governance Quality Gate**: [`docs/en/validation/regulated-action-governance-quality-gate.md`](docs/en/validation/regulated-action-governance-quality-gate.md)
- **Regulated Action Governance External Review Handoff Pack**: [`docs/en/validation/external-review-handoff-regulated-action-governance.md`](docs/en/validation/external-review-handoff-regulated-action-governance.md)
- **Regulated Action Governance External Reviewer Feedback Template**: [`docs/en/validation/external-reviewer-feedback-template-regulated-action-governance.md`](docs/en/validation/external-reviewer-feedback-template-regulated-action-governance.md)
- **Required Evidence Taxonomy v0**: [`docs/en/governance/required-evidence-taxonomy.md`](docs/en/governance/required-evidence-taxonomy.md)
- **AML/KYC contract hardening (canonical gate + evidence profile)**: [`docs/en/guides/financial-governance-templates.md`](docs/en/guides/financial-governance-templates.md)
- **Documentation Map**: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)
- **Operations Runbook**: [`docs/ja/operations/enterprise_slo_sli_runbook_ja.md`](docs/ja/operations/enterprise_slo_sli_runbook_ja.md)
- **Governance Signing Runbook**: [`docs/en/operations/governance-artifact-signing.md`](docs/en/operations/governance-artifact-signing.md)
- **Governance Upgrade Press Summary**: [`docs/press/governance_control_plane_upgrade_2026-04.md`](docs/press/governance_control_plane_upgrade_2026-04.md)

## AML/KYC Beachhead PoC Pack (what you can run in 1 day)

For regulated teams evaluating VERITAS OS in AML/KYC workflows, the beachhead
pack is documented as an executable path, not only positioning text:

1. Run the 1-day PoC fixture set and quantify pass/fail/warning outcomes.
2. Review operator checkpoints (fail-closed gate, evidence-first deltas, replay
   consistency).
3. Produce evidence-bundle handoff artifacts for external review readiness.

Start here:
- [1-day PoC Quickstart](docs/en/guides/poc-pack-financial-quickstart.md)
- Deterministic fixture scenario: `scripts/run_aml_kyc_poc_fixture.py` with `veritas_os/sample_data/governance/aml_kyc_poc_pack/`
- [Financial Governance Templates](docs/en/guides/financial-governance-templates.md)
- [External Audit Readiness](docs/en/validation/external-audit-readiness.md)
- [Short Positioning by audience](docs/en/positioning/aml-kyc-beachhead-short-positioning.md)

## 🚀 Quick Start (TL;DR)

```bash
# Clone & start with Docker Compose (recommended)
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os
cp .env.example .env        # Edit: set OPENAI_API_KEY, VERITAS_API_KEY, VERITAS_API_SECRET
docker compose up --build

# Backend: http://localhost:8000 (Swagger UI: /docs)
# Frontend: http://localhost:3000 (Mission Control)
# PostgreSQL: localhost:5432 (auto-configured as default storage backend)
```

> **Docker Compose defaults to PostgreSQL** for both Memory and TrustLog backends.
> Verify with: `curl -s http://localhost:8000/health | python3 -c "import json,sys; print(json.load(sys.stdin)['storage_backends'])"`
>
> To use lightweight file-based backends instead, set in your `.env`:
> ```
> VERITAS_MEMORY_BACKEND=json
> VERITAS_TRUSTLOG_BACKEND=jsonl
> ```

> **Prerequisites**: Docker 20+ and Docker Compose v2. For local dev: Python 3.11+, Node.js 20+, pnpm.

## PostgreSQL Production Path & Validation Status

For this repository, **PostgreSQL backend is the formal production path** for both
MemoryOS and TrustLog. JSON/JSONL backends remain available for local lightweight
development and migration workflows, not as the recommended production baseline.

- **Default in Docker Compose:** `VERITAS_MEMORY_BACKEND=postgresql` and
  `VERITAS_TRUSTLOG_BACKEND=postgresql` are set in `docker-compose.yml`.
- **Runtime verification point:** check `/health` → `storage_backends` to confirm the
  active backend at runtime.
- **Live PostgreSQL validation exists in multiple layers:** CI smoke (`pytest -m smoke`),
  production-like validation (`pytest -m "production or smoke"`), and live validation
  entry points (`make validate-postgresql-live`, `make validate-live`, workflow `production-validation.yml`).

Verification-oriented docs:

- [`docs/en/validation/postgresql-production-proof-map.md` — compact reviewer entrypoint for production-path proof, automation evidence, and guarantee boundary](docs/en/validation/postgresql-production-proof-map.md)
- [`docs/en/validation/backend-parity-coverage.md` — canonical parity/implementation verification source](docs/en/validation/backend-parity-coverage.md)
- [`docs/en/validation/production-validation.md` — canonical tier/promotion/release-gate source](docs/en/validation/production-validation.md)
- [`docs/en/operations/postgresql-production-guide.md` — canonical PostgreSQL operations/monitoring/recovery source](docs/en/operations/postgresql-production-guide.md)
- [`docs/live-postgresql-validation.md` — canonical public evidence entrypoint for live PostgreSQL validation](docs/live-postgresql-validation.md)

### Guarantee boundary (current)

- **Guaranteed:** PostgreSQL is the documented production path, Docker Compose defaults
  to PostgreSQL, backend parity expectations are documented, and production validation
  documentation includes continuous/live validation paths.
- **Not guaranteed yet:** this README section alone does not guarantee environment-specific
  HA/DR posture, cloud-managed service configuration correctness, or operator runbook
  execution quality in your target production environment.

## Contents

- [Beta at a Glance](#-beta-at-a-glance)
- [Why VERITAS?](#-why-veritas)
- [What It Does](#-what-it-does)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Frontend — Mission Control Dashboard](#-frontend--mission-control-dashboard)
- [API Overview](#-api-overview)
- [Docker Compose (Full Stack)](#-docker-compose-full-stack)
- [Docker (Backend Only)](#-docker-backend-only)
- [Architecture (High-Level)](#-architecture-high-level)
- [TrustLog (Hash-Chained Audit Log)](#-trustlog-hash-chained-audit-log)
- [Continuation Runtime](#-continuation-runtime)
- [Tests](#-tests)
- [Environment Variables Reference](#-environment-variables-reference)
- [Security Notes (Important)](#-security-notes-important)
- [Roadmap (Near-Term)](#-roadmap-near-term)
- [License](#-license)
- [Contributing](#-contributing)
- [Citation (BibTeX)](#-citation-bibtex)

---

## 📊 Beta at a Glance

| Area | Current beta posture |
|---|---|
| Core decision path | End-to-end `/v1/decide` pipeline is implemented with orchestration, gating, persistence, and replay hooks. |
| Governance | Policy updates, approval workflow, audit trail, and compliance export paths are already first-class. |
| Frontend | Mission Control is feature-rich enough for operator workflows, not just a demo shell. |
| Safety stance | Fail-closed behavior is preferred over permissive fallback across FUJI-, replay-, and TrustLog-adjacent flows. |
| Deployment expectation | Suitable for evaluation, staging, internal pilots, and guarded beta programs; production use still requires environment-specific hardening and operational review. |

**What "beta" means here**
- The architecture is broad and already integrated across backend, frontend, replay, governance, and compliance surfaces.
- The project is **not** positioned as an alpha prototype anymore; it already contains substantial operational and audit infrastructure.
- You should still expect active iteration in policy packs, deployment defaults, and environment-specific integrations.

## 🔒 Runtime Posture Guarantees

VERITAS OS uses a single **runtime posture** (`VERITAS_POSTURE`) to control governance-critical defaults.  Set it once; every safety flag derives from it.

| Posture | Governance controls | Startup behaviour | Escape hatches |
|---|---|---|---|
| **dev** (default) | All off unless explicitly enabled | Relaxed — warnings only | N/A |
| **staging** | All off unless explicitly enabled | Relaxed — warnings only | N/A |
| **secure** | All **on** by default | Fail-closed — refuses on missing integrations | `VERITAS_POSTURE_OVERRIDE_*` accepted |
| **prod** | All **on**, no exceptions | Fail-closed — refuses on missing integrations | Overrides are **ignored** |

### Controls governed by posture

| Control | Env var (explicit override) | What it enforces |
|---|---|---|
| Policy runtime enforcement | `VERITAS_POLICY_RUNTIME_ENFORCE` | Compiled policy deny/halt/escalate/require_human_review decisions enforced in pipeline |
| External secret manager | `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER` | Require Vault/KMS/cloud secret manager at startup |
| Transparency log anchoring | `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` | TrustLog writes fail when transparency anchor is missing |
| WORM hard-fail | `VERITAS_TRUSTLOG_WORM_HARD_FAIL` | TrustLog writes fail when WORM mirror write fails |
| Strict replay | `VERITAS_REPLAY_STRICT` | Critical replay divergences abort |
| Governance artifact signatures | `VERITAS_POLICY_VERIFY_KEY` (+ posture strictness) | In secure/prod, reject unsigned or non-Ed25519 governance policy bundles |

### Governance artifact identity in decision outputs

When compiled policy governance is active, `/v1/decide` responses include
`governance_identity` with:

- `policy_version`
- `digest` (compiled bundle semantic hash)
- `signature_verified`
- `signer_id` (if bundle metadata provides `signing.key_id`)
- `verified_at`

This identity is threaded into decision, replay, and audit artifacts so that
operators can prove which governance control-plane asset was in force.

### What causes startup refusal (secure/prod)

The startup validator uses a **capability-aware** model.  Rather than
checking vendor names directly, it verifies that each configured backend
declares the security capabilities required by the posture.  Startup will
refuse with an actionable error when any required capability is missing:

| Required capability | What it means | Current implementation |
|---|---|---|
| `managed_signing` | Signing key material held in a managed HSM/KMS | `aws_kms` signer backend |
| `immutable_retention` | Tamper-proof, append-only retention enforced by storage service | `s3_object_lock` mirror backend |
| `transparency_anchoring` | Verifiable proof-of-existence anchor (when required) | `local` / `tsa` anchor backends |
| `fail_closed` | Errors result in hard refusal, never silent pass | All secure/prod backends |

Additionally, startup refuses when:
- `VERITAS_SECRET_PROVIDER` is not set (external secret manager enforcement)
- `VERITAS_API_SECRET_REF` is not set (external secret manager enforcement)
- Backend-specific configuration is incomplete (e.g. missing `VERITAS_TRUSTLOG_KMS_KEY_ID` for `aws_kms`, missing S3 bucket/prefix for `s3_object_lock`)

> **Note:** In `prod` posture, `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD`
> is unconditionally ignored — there is no break-glass for insecure signers in
> production.  In `secure` posture this override remains available as an
> unsupported emergency escape hatch.

### Escape hatches (secure posture only)

In `secure` posture, individual controls may be disabled for pre-production testing:
```bash
VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE=0
VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR=0
VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY=0
VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM=0
VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT=0
```
These overrides are **silently ignored** in `prod` posture.

## 🎯 Why VERITAS?

Most "agent frameworks" optimize autonomy and tool use.
VERITAS optimizes for **governance**:

- **Fail-closed safety & compliance** enforced by a final gate (**FUJI Gate**) with PII detection, harmful content blocking, prompt injection defense, toxicity filtering for web search results, and policy-driven rules — all safety paths return `rejected` / `risk=1.0` on exception (fail-closed)
- **High-fidelity reproducible decision pipeline** (17 traced stages, structured outputs, replay with divergence detection, retrieval snapshot checksum, model version verification)
- **Auditability** via a **hash-chained TrustLog** (tamper-evident, Ed25519-signed, WORM hard-fail mirror, **Transparency log anchor**, **W3C PROV export**)
- **Enterprise governance** — **4-eyes approval** for policy changes, **RBAC/ABAC** access control, **SSE real-time governance alerts**, external secret manager enforcement
- **Memory & world state** as first-class inputs (MemoryOS with vector search + WorldModel with causal transitions)
- **Operational visibility** via a full-stack **Mission Control dashboard** (Next.js) with real-time event streaming, risk analytics, and governance policy management
- **Bind-boundary visibility** in Mission Control via bind-phase outcomes (`COMMITTED`/`BLOCKED`/`ESCALATED`/`ROLLED_BACK`/`APPLY_FAILED`/`SNAPSHOT_FAILED`/`PRECONDITION_FAILED`) with execution intent and bind receipt lineage pointers
- **EU AI Act compliance** — built-in compliance reporting, audit export, and deployment readiness checks

**Target users**
- AI safety / agent researchers
- Teams operating LLMs in regulated or high-stakes environments
- Governance / compliance teams building "policy-driven" LLM systems

---

## 💡 What It Does

### `/v1/decide` — Full Decision Loop (Structured JSON)

`POST /v1/decide` returns a structured decision record.

Key fields (simplified):

| Field | Meaning |
|---|---|
| `chosen` | Selected action + rationale, uncertainty, utility, risk |
| `alternatives[]` | Other candidate actions |
| `evidence[]` | Evidence used (MemoryOS / WorldModel / web search) |
| `critique[]` | Self-critique & weaknesses |
| `debate[]` | Pro/con/third-party viewpoints |
| `telos_score` | Alignment score vs ValueCore |
| `fuji` | FUJI Gate result (allow / modify / rejected) |
| `gate.decision_status` | Normalized final status (`DecisionStatus`) |
| `gate_decision` | Public gate outcome (`allow`/`hold`/`deny`/`block`...). `allow` means response generation can proceed, **not** case approval. |
| `business_decision` | Case lifecycle status (`APPROVE`/`HOLD`/`REVIEW_REQUIRED`/`DENY`/...) |
| `next_action` | Recommended next operator/system action (separate from business state) |
| `required_evidence[]` | Evidence keys required by current policy/risk boundary |
| `human_review_required` | Explicit human-review requirement flag |
| `trust_log` | Hash-chained TrustLog entry (`sha256_prev`) |
| `bind_outcome` | Bind-phase terminal outcome (`COMMITTED` / `BLOCKED` / `ESCALATED` / `ROLLED_BACK` / `APPLY_FAILED` / `SNAPSHOT_FAILED` / `PRECONDITION_FAILED`) |
| `execution_intent_id` | Lineage pointer to bind attempt context |
| `bind_receipt_id` | Lineage pointer to TrustLog-linked bind receipt artifact |
| `bind_failure_reason` | Operator-facing reason when bind-phase is blocked/escalated/rolled back/fails safely |
| `extras.metrics` | Per-stage latency, memory hits, web hits |

Decision output semantics:

- **FujiGate** owns safety/policy gate adjudication and emits `gate_decision`.
- **Value Core** compares option value and informs `business_decision` + `next_action`.
- UI must show `gate_decision`, `business_decision`, and `next_action` as different concepts.
- `allow` is gate-level permissive status only; it must not be presented as case approval.
- Bind-phase outcomes (`COMMITTED`/`BLOCKED`/`ESCALATED`/`ROLLED_BACK`/`APPLY_FAILED`/`SNAPSHOT_FAILED`/`PRECONDITION_FAILED`) are a separate adjudication layer from decision-phase approval.
- Financial/regulatory governance prompt templates are available as canonical fixtures for
  regression and demo workflows (`veritas_os/sample_data/governance/financial_regulatory_templates.json`);
  see `docs/en/guides/financial-governance-templates.md`.

Pipeline stages:

```text
Input Normalize → Memory Retrieval → Web Search → Options Normalize
  → Core Execute → Absorb Results → Fallback Alternatives → Model Boost
  → Debate → Critique → FUJI Precheck → ValueCore → Gate Decision
  → Value Learning (EMA) → Compute Metrics → Evidence Hardening
  → Response Assembly → Persist (Audit + Memory + World) → Finalize Evidence
  → Build Replay Snapshot
```

Bundled subsystems:

### Responsibility boundaries that matter

These boundaries are enforced in code and tests, and they are important when extending the system:

| Component | Owns | Should not absorb | Recommended extension direction |
|---|---|---|---|
| **Planner** | Planning structure, action-plan generation, planner-oriented summaries | Kernel orchestration, FUJI policy logic, Memory persistence internals | Planner helpers / planner normalization layers |
| **Kernel** | Decision computation, scoring, debate wiring, rationale assembly | API orchestration, persistence, direct governance storage concerns | Kernel stages / QA helpers / contracts |
| **FUJI** | Final safety and policy gating, rejection semantics, audit-facing gate status | Memory management, planner branching, general persistence workflows | FUJI policy, safety-head, and helper modules |
| **MemoryOS** | Memory storage, retrieval, summarization, lifecycle, security controls | Planner policy, kernel decision policy, FUJI gate logic | Memory store / search / lifecycle / security helpers |

This separation is one of the reasons VERITAS is easier to audit and safer to evolve than a single-file "agent loop."

| Subsystem | Purpose |
|---|---|
| **MemoryOS** | Episodic/semantic/procedural/affective memory with vector search (sentence-transformers), retention classes, legal hold, and PII masking |
| **WorldModel** | World state snapshots, causal transitions, project scoping, hypothetical simulation |
| **ValueCore** | Value function with 14 weighted dimensions (9 core ethical + 5 policy-level), online learning via EMA, auto-rebalancing from TrustLog feedback. Context-aware domain profiles (medical/financial/legal/safety), policy-aware score floors (strict/balanced/permissive), per-factor contribution explainability, and auditable weight adjustment trail |
| **FUJI Gate** | Multi-layer safety gate — PII detection, harmful content blocking, sensitive domain filtering, prompt injection defense, confusable character detection, LLM safety head, and policy-driven YAML rules |
| **TrustLog** | Append-only hash-chained audit log (JSONL) with SHA-256 integrity, Ed25519 signatures, WORM hard-fail mirror, Transparency log anchor, and automatic PII data classification |
| **Debate** | Multi-viewpoint reasoning (pro/con/third-party) for transparent decision rationale |
| **Critique** | Self-critique generation with severity-ranked issues and fix suggestions |
| **Planner** | Action plan generation with step-by-step execution strategies |
| **Replay Engine** | High-fidelity reproducible replay of past decisions with diff reporting, retrieval snapshot checksum, model version verification, and dependency version tracking for audit verification |
| **Policy Compiler** | YAML/JSON policy → intermediate representation → compiled rules with Ed25519-signed bundles, runtime enforcement adapter, and auto-generated tests |
| **Compliance** | EU AI Act compliance reports, internal governance reports, and deployment readiness checks |

---

## 📁 Project Structure

```text
veritas_os/                  ← Monorepo root
├── veritas_os/              ← Python backend (FastAPI)
│   ├── api/                 ← REST API server, schemas, governance
│   │   ├── server.py        ← FastAPI app with 37 endpoints
│   │   ├── routes_decide.py ← Decision & replay endpoints
│   │   ├── routes_trust.py  ← TrustLog & audit endpoints
│   │   ├── routes_memory.py ← Memory CRUD endpoints
│   │   ├── routes_governance.py ← Governance & policy endpoints
│   │   ├── routes_system.py ← Health, metrics, compliance, SSE, halt
│   │   ├── schemas.py       ← Pydantic v2 request/response models
│   │   └── governance.py    ← Policy management with audit trail
│   ├── core/                ← Decision engine
│   │   ├── kernel.py        ← Decision computation engine
│   │   ├── kernel_*.py      ← Kernel extensions (doctor, intent, QA, stages, episode, post_choice)
│   │   ├── pipeline/        ← 17-stage orchestrator (package with stage modules)
│   │   ├── fuji/            ← FUJI safety gate (package — policy, injection, safety head)
│   │   ├── memory/          ← MemoryOS (package — store, vector, search, security, compliance)
│   │   ├── continuation_runtime/ ← Chain-level continuation observation (Phase-1)
│   │   ├── value_core.py    ← Value alignment & online learning
│   │   ├── world.py         ← WorldModel (state management)
│   │   ├── llm_client.py    ← Multi-provider LLM gateway
│   │   ├── debate.py        ← Debate mechanism
│   │   ├── critique.py      ← Critique generation
│   │   ├── planner.py       ← Action planning (+ planner_helpers, planner_json, planner_normalization)
│   │   └── sanitize.py      ← PII masking & content safety
│   ├── policy/              ← Policy compiler, signing, runtime adapter, bundle
│   ├── logging/             ← TrustLog, dataset writer, encryption, rotation
│   ├── audit/               ← Signed audit log (Ed25519)
│   ├── compliance/          ← EU AI Act report engine
│   ├── security/            ← SHA-256 hashing, Ed25519 signing
│   ├── tools/               ← Web search, GitHub search, LLM safety
│   ├── replay/              ← Deterministic replay engine
│   ├── observability/       ← OpenTelemetry metrics, middleware
│   ├── storage/             ← Pluggable storage backends (JSONL, PostgreSQL, Alembic migrations)
│   ├── prompts/             ← Prompt templates for LLM interactions
│   ├── reporting/           ← Report generation utilities
│   ├── benchmarks/          ← Performance benchmark data
│   └── tests/               ← 6600+ Python tests (+ top-level tests/)
├── frontend/                ← Next.js 16 Mission Control dashboard
│   ├── app/                 ← Pages (Home, Console, Audit, Governance, Risk)
│   ├── components/          ← Shared React components
│   ├── features/console/    ← Decision Console feature module
│   ├── lib/                 ← API client, validators, utilities
│   ├── locales/             ← i18n (Japanese / English)
│   └── e2e/                 ← Playwright E2E tests
├── packages/
│   ├── types/               ← Shared TypeScript types & runtime validators
│   └── design-system/       ← Card, Button, AppShell components
├── spec/                    ← OpenAPI specification (MIT)
├── sdk/                     ← SDK interface layer (MIT)
├── cli/                     ← CLI interface layer (MIT)
├── policies/                ← Policy templates (examples are MIT)
├── config/                  ← Test and runtime configuration
├── scripts/                 ← Architecture, quality, and security validation scripts
├── docs/                    ← Architecture docs, reviews, user manual, coverage reports
├── openapi.yaml             ← OpenAPI 3.x specification
├── docker-compose.yml       ← Full-stack orchestration
├── Makefile                 ← Dev/test/deploy commands
└── pyproject.toml           ← Python project config
```

---

## 💾 Storage Backends

VERITAS OS uses a **pluggable storage backend** pattern for MemoryOS and TrustLog persistence.

> **Positioning:** PostgreSQL is the official production backend path in this repository.
> JSON/JSONL is retained for local/dev and migration compatibility workflows.

| Backend | MemoryOS | TrustLog | Default (local/CLI) | Default (Docker Compose) | Use case |
|---------|----------|----------|:-------------------:|:------------------------:|----------|
| **JSON / JSONL** (file-based) | `JsonMemoryStore` | `JsonlTrustLogStore` | ✅ Yes | — | Single-process dev, demo, air-gapped |
| **PostgreSQL** | `PostgresMemoryStore` | `PostgresTrustLogStore` | — | ✅ Yes | Multi-worker production, durable audit |

> **Docker Compose defaults to PostgreSQL.** File-based backends are the default
> when running via `python -m veritas_os` or `uvicorn` without overriding env vars.

### Environment matrix

| Environment | Recommended backend | Config source |
|-------------|-------------------|---------------|
| Local dev (no Docker) | JSON / JSONL | `.env` defaults |
| Local dev (Docker Compose) | PostgreSQL | `docker-compose.yml` defaults |
| Staging | PostgreSQL | Explicit env vars |
| Secure / Prod | PostgreSQL | External secret manager |

### Quick switch

```bash
# Use PostgreSQL for both backends
VERITAS_MEMORY_BACKEND=postgresql
VERITAS_TRUSTLOG_BACKEND=postgresql
VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas

# Apply schema
make db-upgrade
```

### Migrating existing data (JSONL → PostgreSQL)

```bash
# 1. Dry-run to validate source files
veritas-migrate trustlog --source runtime/trustlog/trust_log.jsonl --dry-run
veritas-migrate memory   --source runtime/memory/memory.json      --dry-run

# 2. Import with post-migration hash-chain verification
veritas-migrate trustlog --source runtime/trustlog/trust_log.jsonl --verify
veritas-migrate memory   --source runtime/memory/memory.json

# 3. Verify via smoke tests
VERITAS_MEMORY_BACKEND=postgresql VERITAS_TRUSTLOG_BACKEND=postgresql \
  pytest -m smoke veritas_os/tests/ -q
```

The `veritas-migrate` CLI is **idempotent** — re-running after a partial failure
safely resumes by skipping already-imported entries. See
[`docs/postgresql-production-guide.md` §11](docs/en/operations/postgresql-production-guide.md)
for the full procedure including rollback.

### Verification tools

| Tool | Purpose | Invocation |
|------|---------|------------|
| `veritas-trustlog-verify` | Standalone TrustLog chain integrity verifier | `veritas-trustlog-verify --log-dir <path>` |
| `veritas-migrate --verify` | Post-import hash-chain check (PostgreSQL) | `veritas-migrate trustlog --source … --verify` |
| `/v1/trustlog/verify` | REST API chain verification | `curl -H "X-API-Key: …" http://host:8000/v1/trustlog/verify` |
| `/v1/metrics` | Pool utilization, health, pg_stat_activity | `curl -H "X-API-Key: …" http://host:8000/v1/metrics` |
| `drill_postgres_recovery.sh` | End-to-end backup → restore → verify | `make drill-recovery` or `make drill-recovery-ci` |
| `pytest -m smoke` | Governance invariant smoke tests | `pytest -m smoke veritas_os/tests/` |
| `pytest -m production` | Production-like validation suite | `make test-production` |

### Key features of the PostgreSQL backend

- **Alembic-managed schema** — reproducible migrations with `upgrade` / `downgrade` paths.
- **Advisory-lock chain serialization** — TrustLog hash-chain integrity guaranteed under concurrent writes via `pg_advisory_xact_lock`.
- **JSONB storage** — queryable payloads with GIN indexes.
- **Full parity test suite** — 195+ tests verify identical semantics across backends.
- **psycopg 3** — modern async PostgreSQL driver with connection pooling (`psycopg-pool`).
- **JSONL → PostgreSQL import** — idempotent `veritas-migrate` CLI with dry-run, resume, and post-import hash-chain verification.
- **Contention testing** — 25 tests in `test_pg_trustlog_contention.py` verify chain integrity under concurrent/burst/failure scenarios.
- **Observability** — `/v1/metrics` exposes pool utilization, health, and `pg_stat_activity` (long-running queries, idle-in-tx, advisory lock waiters). 28 tests in `test_pg_metrics.py`.
- **Recovery drill** — `scripts/drill_postgres_recovery.sh` automates backup → restore → verify cycle. 31 tests in `test_drill_postgres_recovery.py`.

### Production deployment

See [`docs/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md) for:
- Pool sizing, SSL/TLS, statement timeout configuration
- Backup/restore, replication/HA guidance
- JSONL → PostgreSQL import via `veritas-migrate` CLI (dry-run, resume, rollback, verification)
- Smoke test and release validation relationship
- Legacy path cleanup status
- Secure/prod posture recommended settings
- Contention test coverage and known limitations
- Metrics reference (JSON fields, Prometheus gauges, interpretation guide)
- Known limitations and future work (pgvector, partitioning, CDC)

See [`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md) for:
- Backup / restore / recovery drill procedures and scripts
- Safe / unsafe HA boundaries for TrustLog writes
- Incident response playbooks (corruption, tampering)
- `make drill-backup`, `make drill-restore`, `make drill-recovery`, `make drill-recovery-ci`

See also: [`docs/database-migrations.md`](docs/en/operations/database-migrations.md) | [`docs/BACKEND_PARITY_COVERAGE.md`](docs/en/validation/backend-parity-coverage.md) | [`docs/legacy-path-cleanup.md`](docs/en/operations/legacy-path-cleanup.md)

---

## 🖥️ Frontend — Mission Control Dashboard

The frontend is a **Next.js 16** (React 18, TypeScript) dashboard that provides operational visibility into the decision pipeline.

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16.2.3 (App Router) |
| Language | TypeScript 5.7 |
| Styling | Tailwind CSS 3.4 + CVA (class-variance-authority) |
| Icons | Lucide React |
| Testing | Vitest + Testing Library (unit), Playwright + axe-core (E2E + accessibility) |
| i18n | Custom React Context (Japanese default, English) |
| Security | CSP with per-request nonce, httpOnly BFF cookies, HSTS, X-Frame-Options |
| Design System | `@veritas/design-system` (Card, Button, AppShell) |
| Shared Types | `@veritas/types` with runtime type guards |
| Lint Config | eslint-config-next 15.5.10 |

### Pages

| Route | Page | Description |
|---|---|---|
| `/` | **Command Dashboard** | Live event stream (FUJI rejects, policy updates, chain breaks), global health summary, critical rail metrics, operational priorities |
| `/console` | **Decision Console** | Interactive decision pipeline — enter a query, watch 8-stage pipeline execute in real-time, view FUJI gate decision, chosen/alternatives/rejected, cost-benefit analysis, replay diff |
| `/audit` | **TrustLog Explorer** | Browse hash-chained audit trail, verify chain integrity (verified/broken/missing/orphan), stage filtering, regulatory report export (JSON/CSV with PII redaction) |
| `/governance` | **Governance Control** | Edit FUJI rules (8 safety gates), risk thresholds, auto-stop circuit breaker, log retention. Standard and EU AI Act modes. Draft → approval workflow with diff viewer and version history |
| `/risk` | **Risk Dashboard** | 24-hour streaming risk/uncertainty chart, severity clustering, flagged request drilldown, anomaly pattern analysis |

### Architecture

- **BFF (Backend-for-Frontend)** pattern: all API requests proxied through Next.js (`/api/veritas/*`), browser never sees API credentials
- **httpOnly session cookie** (`__veritas_bff`) for authentication, scoped to `/api/veritas/*`
- **Runtime type guards** validate every API response before rendering (`isDecideResponse`, `isTrustLogsResponse`, `validateGovernancePolicyResponse`, etc.)
- **SSE + WebSocket** for real-time event streaming (live FUJI rejects, trust log updates, risk bursts)
- **XSS defense** via `sanitizeText()` on all API response rendering

---

## 📡 API Overview

All protected endpoints require `X-API-Key`. The full list of endpoints:

### Decision

| Method | Path | Description |
|---|---|---|
| POST | `/v1/decide` | Full decision pipeline |
| POST | `/v1/fuji/validate` | Validate a single action via FUJI Gate |
| POST | `/v1/replay/{decision_id}` | Deterministic replay with diff report |
| POST | `/v1/decision/replay/{decision_id}` | Alternative replay with mock support |

### Memory

| Method | Path | Description |
|---|---|---|
| POST | `/v1/memory/put` | Store memory (episodic/semantic/procedural/affective) |
| POST | `/v1/memory/get` | Retrieve memory by key |
| POST | `/v1/memory/search` | Vector search with user_id filtering |
| POST | `/v1/memory/erase` | Erase user memories (legal hold protected) |

### Trust & Audit

| Method | Path | Description |
|---|---|---|
| GET | `/v1/trust/logs` | List trust log entries |
| GET | `/v1/trust/{request_id}` | Get single trust log entry |
| POST | `/v1/trust/feedback` | User satisfaction feedback on decisions |
| GET | `/v1/trust/stats` | Trust log statistics |
| GET | `/v1/trustlog/verify` | Verify hash chain integrity |
| GET | `/v1/trustlog/export` | Export signed trustlog |
| GET | `/v1/trust/{request_id}/prov` | W3C PROV-JSON export for audit interoperability |

### Governance

| Method | Path | Description |
|---|---|---|
| GET | `/v1/governance/policy` | Retrieve current governance policy |
| PUT | `/v1/governance/policy` | Update governance policy (hot-reload, **4-eyes approval required**; bind-governed mutation response includes bind lineage fields + `bind_summary`) |
| GET | `/v1/governance/policy/history` | Policy change audit trail (with digest transitions) |
| GET | `/v1/governance/value-drift` | Monitor value weight EMA drift |
| GET | `/v1/governance/decisions/export` | Export decisions for governance audit, including bind lineage fields and additive `bind_summary` vocabulary |
| POST | `/v1/governance/policy-bundles/promote` | Execute policy bundle promotion as a bind-boundary governance workflow (returns bind receipt lineage and additive `bind_summary`; requires governance write permission) |
| GET | `/v1/governance/bind-receipts` | List bind receipts (decision/execution lineage + canonical target/outcome/reason/failed/recent/sort/limit filters) |
| GET | `/v1/governance/bind-receipts/export` | Export bind receipts for operator/audit pipelines using the same filter vocabulary as list |
| GET | `/v1/governance/bind-receipts/{bind_receipt_id}` | Retrieve a single full bind receipt artifact (including canonical target metadata and bind checks) |

#### Bind artifact family: operator meaning

- `BindReceipt` is the full bind artifact used for reviewable/auditable lineage and replay-oriented investigation.
- `bind_summary` is the compact shared bind vocabulary reused across bind-governed mutation and export responses.
- This separation keeps decision approval and bind commitment distinct on the operator-facing governance surface (Mission Control + APIs).


#### Operator workflow: promote a policy bundle

Use `POST /v1/governance/policy-bundles/promote` when you need to promote the active policy bundle pointer via the existing bind-boundary path.

- Request accepts **exactly one** selector: `bundle_id` **or** `bundle_dir_name`.
- Arbitrary filesystem paths are rejected (`/`, `\`, `.`, `..` are not accepted in selectors).
- Response includes bind lineage fields (`bind_outcome`, `bind_receipt_id`, `execution_intent_id`), additive `bind_summary`, and the full `bind_receipt`.
- Use `GET /v1/governance/bind-receipts`, `GET /v1/governance/bind-receipts/export`, or `GET /v1/governance/bind-receipts/{bind_receipt_id}` to inspect/export resulting artifacts.

```bash
curl -X POST "http://127.0.0.1:8000/v1/governance/policy-bundles/promote" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "bundle_id": "bundle-v2",
    "decision_id": "dec-promote-1",
    "request_id": "req-promote-1",
    "policy_snapshot_id": "snap-promote-1",
    "decision_hash": "hash-promote-1"
  }'
```

For operator guidance and outcome interpretation, see
[`docs/en/guides/governance-policy-bundle-promotion.md`](docs/en/guides/governance-policy-bundle-promotion.md).

> **Signed governance artifacts** — In secure/prod posture, policy bundles must be Ed25519-signed.
> Decision artifacts include a `governance_identity` field showing which governance policy was in
> force (version, digest, signature verification result, signer identity).
> See [`docs/governance_artifact_lifecycle.md`](docs/en/governance/governance-artifact-lifecycle.md) for the
> full lifecycle, key management, and migration guide.

### Compliance & Reporting

| Method | Path | Description |
|---|---|---|
| GET | `/v1/report/eu_ai_act/{decision_id}` | EU AI Act compliance report |
| GET | `/v1/report/governance` | Internal governance report |
| GET | `/v1/compliance/deployment-readiness` | Pre-deployment compliance check |
| GET | `/v1/compliance/config` | Retrieve compliance configuration |
| PUT | `/v1/compliance/config` | Update compliance configuration (bind-governed mutation response includes bind lineage fields + `bind_summary`) |

### System

| Method | Path | Description |
|---|---|---|
| GET | `/health`, `/v1/health` | Health check |
| GET | `/status`, `/v1/status` | Extended status with pipeline/config health |
| GET | `/v1/metrics` | Operational metrics |
| GET | `/v1/events` | SSE stream for real-time UI updates |
| WS | `/v1/ws/trustlog` | WebSocket for live trust log streaming |
| POST | `/v1/system/halt` | Emergency halt (persists halt state) |
| POST | `/v1/system/resume` | Resume after halt |
| GET | `/v1/system/halt-status` | Current halt state |

### Replay

`POST /v1/replay/{decision_id}` re-executes a stored decision using the original recorded inputs and writes a replay artifact to `REPLAY_REPORT_DIR` (`audit/replay_reports` by default) as `replay_{decision_id}_{YYYYMMDD_HHMMSS}.json`.

Replay snapshots include `retrieval_snapshot_checksum` (SHA-256 deterministic hash), `external_dependency_versions`, and `model_version` for reproducibility verification. Model version mismatch is checked by default; snapshots without `model_version` are rejected by default (`VERITAS_REPLAY_REQUIRE_MODEL_VERSION=1`).

> **Note**: LLM responses are inherently non-deterministic even at `temperature=0`. VERITAS Replay is designed as **high-fidelity reproducible re-execution with divergence detection**, not strict deterministic replay.

When `VERITAS_REPLAY_STRICT=1`, replay enforces deterministic settings (`temperature=0`, fixed seed, and mocked external retrieval side effects).

```bash
BODY='{"strict":true}'
TS=$(date +%s)
NONCE="replay-$(uuidgen | tr '[:upper:]' '[:lower:]')"
SIG=$(python - <<'PY'
import hashlib
import hmac
import os

secret=os.environ["VERITAS_API_SECRET"].encode("utf-8")
ts=os.environ["TS"]
nonce=os.environ["NONCE"]
body=os.environ["BODY"]
payload=f"{ts}\n{nonce}\n{body}"
print(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest())
PY
)

curl -X POST "http://127.0.0.1:8000/v1/replay/DECISION_ID" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "X-VERITAS-TIMESTAMP: ${TS}" \
  -H "X-VERITAS-NONCE: ${NONCE}" \
  -H "X-VERITAS-SIGNATURE: ${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
```

EU AI Act report generation already reads `replay_{decision_id}_*.json`, so invoking the Replay API updates replay verification data consumed by compliance reporting automatically.

---

## 🚀 Quick Start

### Option A: Docker Compose (Recommended)

Start both backend and frontend with a single command:

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

# Copy and edit environment variables
cp .env.example .env
# Edit .env — set OPENAI_API_KEY, VERITAS_API_KEY, VERITAS_API_SECRET

docker compose up --build
```

- Backend: `http://localhost:8000` (Swagger UI at `/docs`)
- Frontend: `http://localhost:3000` (Mission Control dashboard)

### Option B: Local Development

#### Backend

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[full]"     # all features (recommended)
# pip install -e .           # core-only (API server + OpenAI)
# pip install -e ".[ml]"    # core + ML tooling
```

> See [`docs/dependency-profiles.md`](docs/en/operations/dependency-profiles.md) for all
> install profiles and the dependency classification table.

> [!WARNING]
> Avoid placing secrets directly in shell history. Prefer a `.env` file (git-ignored) or a
> secrets manager for production environments.

Set environment variables (or use a `.env` file):

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
```

Start the backend:

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

#### Frontend

```bash
# From the repository root (requires Node.js 20+ and pnpm)
corepack enable
pnpm install --frozen-lockfile
pnpm ui:dev
```

The frontend starts at `http://localhost:3000`.

Set `VERITAS_API_BASE_URL` if the frontend BFF should reach a backend other than `http://localhost:8000`. Do not set `NEXT_PUBLIC_*` API base URL variables in production because they can expose internal routing details and now trigger BFF fail-closed behavior.

#### Makefile shortcuts

```bash
make setup         # Initialize environment
make dev           # Start backend (port 8000)
make dev-frontend  # Start frontend (port 3000)
make dev-all       # Start both
```

#### Local Mac Development (No Docker)

A validated end-to-end flow for running VERITAS OS natively on macOS without Docker.

**1. Create `.env`** — copy `.env.example` and fill in the required values:

```bash
cp .env.example .env
# Edit .env — set at minimum:
#   OPENAI_API_KEY, VERITAS_API_KEY, VERITAS_API_SECRET, VERITAS_ENCRYPTION_KEY
```

Generate an encryption key if you don't have one:

```bash
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"
```

Add TrustLog WORM mirror and transparency log paths for local dev:

```bash
# Append to .env
VERITAS_TRUSTLOG_MIRROR_BACKEND=local
VERITAS_TRUSTLOG_WORM_MIRROR_PATH=runtime/dev/logs/trustlog_worm.jsonl
VERITAS_TRUSTLOG_ANCHOR_BACKEND=local
VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH=runtime/dev/logs/trustlog_transparency.jsonl
```

**2. Launch backend** — `.env` must be sourced into the shell:

```bash
set -a && source .env && set +a
python -m uvicorn veritas_os.api.server:app --reload --port 8000
# Or simply: make dev   (Makefile sources .env automatically)
```

**3. Launch frontend** — in a separate terminal:

```bash
# Frontend reads frontend/.env.development automatically via Next.js.
# Ensure VERITAS_API_KEY in frontend/.env.development matches your backend.
set -a && source .env && set +a
pnpm ui:dev
```

**4. BFF authentication** — the frontend BFF proxy requires a valid auth token.
`frontend/.env.development` ships with dev defaults (`VERITAS_BFF_AUTH_TOKENS_JSON`
and `VERITAS_BFF_SESSION_TOKEN`). For browser access, visit
`http://localhost:3000/api/auth/dev-login` to mint the `__veritas_bff` httpOnly
cookie, which authenticates all subsequent `/api/veritas/*` requests.

**5. Verified working features:**

| Feature | Endpoint / Path |
|---|---|
| Decision | `POST /v1/decide` |
| SSE events | `GET /v1/events` |
| TrustLog save | Automatic on decide |
| WORM mirror | `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` |
| Transparency log | `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` |

**6. Dev artifact locations** — with default settings, runtime data writes to:

| Path | Contents |
|---|---|
| `runtime/dev/logs/` | TrustLog JSONL, WORM mirror, transparency log |
| `runtime/dev/logs/DASH/` | Shadow decide outputs, datasets |
| `runtime/dev/logs/keys/` | Ed25519 signing key material (auto-generated) |

> [!TIP]
> The `runtime/` directory is namespace-separated (`dev`, `test`, `demo`, `prod`)
> via `VERITAS_RUNTIME_NAMESPACE` or the `VERITAS_ENV` mapping. Default is `dev`.

### Try the API

Open Swagger UI at `http://127.0.0.1:8000/docs`, authorize with `X-API-Key`, and run `POST /v1/decide`:

```json
{
  "query": "Should I check tomorrow's weather before going out?",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"],
    "affect_hint": "focused"
  }
}
```

---

## 🐳 Docker Compose (Full Stack)

`docker-compose.yml` orchestrates three services:

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16 (auto-configured, health-checked, resource-limited) |
| `backend` | 8000 | FastAPI server (built from `Dockerfile`) with health check, depends on `postgres` |
| `frontend` | 3000 | Next.js dev server (Node.js 20), waits for backend to be healthy |

```bash
docker compose up --build   # Start
docker compose down         # Stop
docker compose logs -f      # Follow logs
```

Environment variables (set in `.env` or shell):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `VERITAS_API_KEY` | — | Backend API authentication key |
| `VERITAS_API_SECRET` | `change-me` | HMAC signing secret (32+ chars recommended) |
| `VERITAS_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS allow-list |
| `VERITAS_API_BASE_URL` | `http://backend:8000` | Frontend BFF (server-only) → backend URL |
| `VERITAS_MEMORY_BACKEND` | `postgresql` | Memory storage backend (`json` or `postgresql`) |
| `VERITAS_TRUSTLOG_BACKEND` | `postgresql` | TrustLog storage backend (`jsonl` or `postgresql`) |
| `VERITAS_DATABASE_URL` | `postgresql://veritas:veritas@postgres:5432/veritas` | PostgreSQL connection URL |
| `LLM_PROVIDER` | `openai` | LLM provider |
| `LLM_MODEL` | `gpt-4.1-mini` | LLM model name |

---

## 🐳 Docker (Backend Only)

Pull the latest image:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

Run the API server:

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_API_KEY" \
  -e VERITAS_API_KEY="your-secret-api-key" \
  -e LLM_PROVIDER="openai" \
  -e LLM_MODEL="gpt-4.1-mini" \
  ghcr.io/veritasfuji-japan/veritas_os:latest
```

If your FastAPI entrypoint differs from `veritas_os.api.server:app`, update the
Dockerfile `CMD` accordingly before building the image.

---

## 🏗️ Architecture (High-Level)

```text
┌──────────────────────────────────────────────────────┐
│  Frontend (Next.js 16 / React 18 / TypeScript)       │
│  ┌────────┬──────────┬───────────┬──────────┬──────┐ │
│  │  Home  │ Console  │   Audit   │Governance│ Risk │ │
│  └────┬───┴────┬─────┴─────┬─────┴────┬─────┴──┬───┘ │
│       │ BFF Proxy (httpOnly cookie, CSP nonce)  │     │
│       └─────────────────┬───────────────────────┘     │
└─────────────────────────┼─────────────────────────────┘
                          │ /api/veritas/*
┌─────────────────────────┼─────────────────────────────┐
│  Backend (FastAPI / Python 3.11+)                      │
│       ┌─────────────────┴─────────────────────┐       │
│       │           API Server (server.py)       │       │
│       │   Auth · Rate Limit · CORS · PII mask  │       │
│       └────┬──────┬──────┬──────┬──────┬──────┘       │
│            │      │      │      │      │              │
│  ┌─────────┴┐ ┌───┴───┐ ┌┴─────┐ ┌────┴──┐ ┌────────┴┐│
│  │ Pipeline ││Govern- ││Memory││Trust  ││Compli-  ││
│  │Orchestr. ││ ance   ││ API  ││ API   ││ ance    ││
│  └────┬─────┘└────────┘└──┬───┘└───┬───┘└─────────┘│
│       │                    │       │               │
│  ┌────┴────────────────────┴───────┴────────────┐  │
│  │            Core Decision Engine               │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │ Kernel │ │ Debate │ │Critique│ │Planner │ │  │
│  │  └────┬───┘ └────────┘ └────────┘ └────────┘ │  │
│  │       │                                       │  │
│  │  ┌────┴───┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │  FUJI  │ │Value   │ │MemoryOS│ │ World  │ │  │
│  │  │  Gate  │ │ Core   │ │(Vector)│ │ Model  │ │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ │  │
│  └──────────────────┬───────────────────────────┘  │
│                     │                              │
│  ┌──────────────────┴───────────────────────────┐  │
│  │  Infrastructure                               │  │
│  │  LLM Client · TrustLog · Replay · Sanitize   │  │
│  │  Atomic I/O · Signing · Tools (Web/GitHub)    │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Core execution path

| Module | Responsibility |
|---|---|
| `veritas_os/core/kernel.py` | Decision computation — intent detection, option generation, alternative scoring |
| `veritas_os/core/pipeline/` | 17-stage orchestrator for `/v1/decide` — validation through audit persistence (package with per-stage modules) |
| `veritas_os/core/llm_client.py` | Multi-provider LLM gateway with connection pooling, circuit breaker, retry with backoff |

### Safety & governance

| Module | Responsibility |
|---|---|
| `veritas_os/core/fuji/` | Multi-layer **fail-closed** safety gate — PII, harmful content, sensitive domains, prompt injection, confusable chars, LLM safety head, policy rules. All exceptions return `rejected` / `risk=1.0` |
| `veritas_os/core/value_core.py` | Value function with 14 weighted dimensions (9 core ethical + 5 policy-level), online learning via EMA, auto-rebalance from TrustLog. Supports context-aware domain profiles, policy-aware score floors, per-factor contribution explainability, and auditable weight adjustment trail |
| `veritas_os/api/governance.py` | Policy CRUD with hot-reload, **4-eyes approval** (2 approvers, no duplicates), change callbacks, audit trail, value drift monitoring, **RBAC/ABAC** access control |
| `veritas_os/logging/trust_log.py` | Hash-chain TrustLog `h_t = SHA256(h_{t-1} ∥ r_t)` with thread-safe append |
| `veritas_os/audit/trustlog_signed.py` | Ed25519-signed TrustLog with **WORM hard-fail** mirror, **Transparency log anchor**, automatic **PII data classification** |
| `veritas_os/policy/` | Policy compiler — YAML/JSON → IR → compiled rules, Ed25519-signed bundles, runtime enforcement adapter |

### Memory & world state

| Module | Responsibility |
|---|---|
| `veritas_os/core/memory/` | Unified episodic/semantic/procedural/affective memory with vector search (sentence-transformers, 384-dim), retention classes, legal hold, PII masking |
| `veritas_os/core/world.py` | World state snapshots, causal transitions, project scoping, hypothetical simulation |

### Reasoning

| Module | Responsibility |
|---|---|
| `veritas_os/core/debate.py` | Multi-viewpoint debate (pro/con/third-party) |
| `veritas_os/core/critique.py` | Self-critique with severity-ranked issues and fix suggestions |
| `veritas_os/core/planner.py` | Action plan generation |

### LLM Client

Supports multiple providers via `LLM_PROVIDER` environment variable. Each provider has a **support tier** that indicates its production readiness:

| Tier | Meaning |
|---|---|
| **production** | CI-tested, production-deployment target, covered by SLA |
| **planned** | Code paths implemented but not verified in production; may lag behind upstream API changes |
| **experimental** | Minimal scaffold only; subject to breaking changes; not for production use |

| Provider | Model | Tier |
|---|---|---|
| `openai` | GPT-4.1-mini (default) | **production** |
| `anthropic` | Claude | planned |
| `google` | Gemini | planned |
| `ollama` | Local models | experimental |
| `openrouter` | Aggregator | experimental |

> **Runtime notice**: Using a non-production provider emits a `UserWarning` so callers are aware of the tier boundary.
>
> **Promoting a provider to production** requires: (1) integration test suite with ≥ 90 % path coverage for the provider, (2) successful staging deployment for ≥ 2 weeks, (3) API-compatibility review against upstream changelog, and (4) explicit approval in a pull request.

Features: shared `httpx.Client` with connection pooling (`LLM_POOL_MAX_CONNECTIONS=20`), retry with configurable backoff (`LLM_MAX_RETRIES=3`), response size guard (16 MB), circuit breaker per provider, monkeypatchable for testing.

---

## 🔗 TrustLog (Hash-Chained Audit Log)

TrustLog is a **secure-by-default**, encrypted, hash-chained audit log.

### Security pipeline (per entry)

```text
entry → redact(PII + secrets) → canonicalize(RFC 8785) → chain hash → encrypt → append
```

1. **Redact** — PII (email, phone, address) and secrets (API keys, bearer tokens) are
   automatically masked before any persistence.
2. **Canonicalize** — RFC 8785 canonical JSON ensures deterministic hashing.
3. **Chain hash** — `h_t = SHA256(h_{t-1} || r_t)` provides tamper-evident linking.
4. **Encrypt** — Mandatory at-rest encryption (AES-256-GCM or HMAC-SHA256 CTR-mode).
   Plaintext storage is **not possible** without explicitly opting out.
5. **Append** — Encrypted line written to JSONL with fsync for durability.

### Setup

```bash
# Generate an encryption key (required)
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"

# Set the key (required for TrustLog to function)
export VERITAS_ENCRYPTION_KEY="<generated-key>"
```

> **Warning**: Without `VERITAS_ENCRYPTION_KEY`, TrustLog writes will fail with
> `EncryptionKeyMissing`. This is by design — plaintext audit logs are prohibited.

### Verification

```bash
# Verify hash chain integrity (requires decryption key)
python -m veritas_os.scripts.verify_trust_log
```

Key features:

- **Cryptographic chain** — RFC 8785 canonical JSON, deterministic SHA-256
- **Thread-safe** — RLock protection with atomic file writes
- **Dual persistence** — in-memory cache (max 2000 items) + persistent JSONL ledger
- **Signed export** — Ed25519 digital signatures for tamper-proof distribution
- **Chain verification** — `GET /v1/trustlog/verify` validates the full chain
- **Transparency log anchor** — external log integration for independent audit verification (`VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` for fail-closed operation)
- **WORM hard-fail** — write failures to WORM mirror raise `SignedTrustLogWriteError` (`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`)
- **W3C PROV export** — `GET /v1/trust/{request_id}/prov` returns PROV-JSON for audit tool interoperability
- **PII masking & classification** — automatic PII/secret redaction with data classification tagging (18 PII patterns including email, credit card, phone, address, IP, passport)
- **Frontend visualization** — TrustLog Explorer at `/audit` with chain integrity status (verified/broken/missing/orphan)

---

## 🔄 Continuation Runtime

VERITAS includes a **chain-level continuation observation and limited enforcement layer** that runs beside (not inside) the existing step-level decision infrastructure.

### Modes

| Mode | Behavior | Default in posture |
|---|---|---|
| **Observe** (Phase-1) | Shadow only — no enforcement, no refusal gating | dev, staging |
| **Advisory** (Phase-2) | Emits enforcement events as advisories; no blocking | secure, prod |
| **Enforce** (Phase-2) | Limited enforcement: may block/halt for high-confidence conditions | (opt-in via env) |

| Aspect | Status |
|---|---|
| FUJI | Unchanged — remains the final safety/policy gate for each step |
| `gate.decision_status` | Unchanged — no new values, no reinterpretation |
| Feature flag off | Zero change to response, logs, UI, or behavior |
| Purpose | Detect and (optionally) enforce when a chain's continuation standing weakens |

### Enforcement Actions (Phase-2)

The enforcement engine triggers only for **high-confidence, explainable conditions**:

| Condition | Action | When |
|---|---|---|
| Repeated high-risk degradation | `require_human_review` | ≥3 consecutive degraded/escalated/halted receipts |
| Approval-required without approval | `halt_chain` | Scope requires escalation but no approval provided |
| Replay divergence exceeded | `escalate_alert` | Divergence ratio >0.3 for sensitive paths |
| Policy boundary violation | `halt_chain` | Policy violation detected in continuation state |

### What causes `require_human_review` vs `halt_chain`?

- **`require_human_review`**: Triggered by *accumulated degradation* — a pattern of weakening that suggests drift, not a single critical failure. The chain is paused pending operator review.
- **`halt_chain`**: Triggered by *deterministic governance failures* — missing approval for an approval-required transition, or a detected policy boundary violation. The chain is stopped immediately.
- **`escalate_alert`**: Triggered by *replay divergence* — the continuation path is diverging from expected replay behavior, suggesting environmental or configuration drift.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `0` | Enable Continuation Runtime |
| `VERITAS_CONTINUATION_ENFORCEMENT_MODE` | `observe` | Enforcement mode (`observe`, `advisory`, `enforce`) |

Posture-based defaults:
- **dev/staging**: `observe` (no enforcement)
- **secure/prod**: `advisory` (emit events, no blocking)
- Set `VERITAS_CONTINUATION_ENFORCEMENT_MODE=enforce` to enable limited enforcement in any posture.

### Key Concepts

- **Snapshot** (state): minimal governable facts — support basis, scope, burden, headroom, law version
- **Receipt** (audit witness): how revalidation was conducted, divergence flags, reason codes, receipt chain linkage
- **Enforcement Event** (audit artifact): every enforcement action is logged, attributable, replay-visible, and operator-visible
- The snapshot is not a receipt. The receipt is not a state store. Enforcement events are separate from both.
- Revalidation runs **before** step-level merit evaluation (pre-merit placement)
- Continuation-level enforcement is conceptually separate from FUJI step-level safety gating

### Every Enforcement Event Is:
- **Logged** — via Python logging + trustlog-ready structure
- **Attributable** — carries `claim_lineage_id`, `receipt_id`, `chain_id`
- **Replay-visible** — carries `snapshot_id`, `receipt_id`, `law_version`
- **Operator-visible** — carries `action`, `reasoning`, `severity`, `conditions_met`

### Design Note

See: `docs/architecture/continuation_enforcement_design_note.md`

Enable with: `VERITAS_CAP_CONTINUATION_RUNTIME=1` (default: off)

See also: `docs/architecture/continuation_runtime_adr.md`, `docs/architecture/continuation_runtime_architecture_note.md`

---

## 🧪 Tests

### Backend (Python)

Recommended (reproducible via `uv`):

```bash
make test
make test-cov
```

These targets use `uv` with `PYTHON_VERSION=3.12.12` and automatically download the
interpreter if it is not already installed. `make test-cov` now mirrors the CI
coverage gate (`--cov-fail-under=85`, `veritas_os/tests/.coveragerc`, XML/HTML reports,
and `-m "not slow"`).

```bash
# Optional: override the local gate/marker to troubleshoot
make test-cov COVERAGE_FAIL_UNDER=0 PYTEST_MARKEXPR=""
```

Fast smoke check:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_api_constants.py"
```

Optional overrides:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_time_utils.py"
make test PYTHON_VERSION=3.11
```

### Frontend (TypeScript)

```bash
# Unit tests (Vitest + Testing Library)
pnpm ui:test

# Type checking
pnpm ui:typecheck

# E2E tests (Playwright + axe-core accessibility)
pnpm --filter frontend e2e:install
pnpm --filter frontend e2e
```

### CI / Quality Gate

VERITAS OS uses a **three-tier CI/release validation model** with explicit blocking semantics:

| Tier | Workflow | Trigger | Blocking? |
|------|----------|---------|-----------|
| **Tier 1** | `main.yml` | Every PR + push to `main` | ✅ Blocks merge |
| **Tier 2** | `release-gate.yml` | `v*` tag push | ✅ Blocks release |
| **Tier 3** | `production-validation.yml` | Weekly + manual | ⚠️ Advisory |

Additional CI workflows:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `codeql.yml` | PR + push to `main` | CodeQL security analysis |
| `publish-ghcr.yml` | Release / tag push | Docker image publishing to GHCR |
| `security-gates.yml` | PR + push to `main` | Security gate checks (dependency audit, secret scanning) |
| `runtime-pickle-guard.yml` | PR + push to `main` | Block runtime pickle/joblib artifacts |
| `sbom-nightly.yml` | Nightly schedule | SBOM generation and vulnerability scan |

**Tier 1** (`main.yml`) — every PR is blocked until all of the following pass:
- Ruff lint + Bandit + architecture/security script checks
- Dependency CVE audit (Python + Node)
- **`governance-smoke`**: explicit fast smoke gate (`pytest -m smoke`, ~2 min)
- Full unit test matrix (Python 3.11 + 3.12, 85% coverage gate)
- Frontend lint / Vitest / Playwright E2E

**Tier 2** (`release-gate.yml`) — every `v*` tag is blocked until all of the following pass:
- Tier 1 checks repeated at release time
- Production-like test suite (`pytest -m "production or smoke"` + TLS + load)
- Full-stack Docker Compose health check
- Governance readiness report artifact generated and uploaded
- Human-readable `release-proof-summary.md` generated for enterprise review / diligence handoff

**Tier 3** (`production-validation.yml`) — weekly schedule + manual dispatch:
- Long-running production tests, load tests, external live tests
- Includes live-provider validation entry points used for ongoing PostgreSQL-backed
  production-path operational verification
- Advisory: failures are visible but do not block release

See [`docs/PRODUCTION_VALIDATION.md`](docs/en/validation/production-validation.md) for the complete
tier model and [`docs/RELEASE_PROCESS.md`](docs/en/operations/release-process.md) for the release process.

### How to tell if a release is governance-ready

1. Find the `Release Gate` workflow run for the target tag in the [Actions tab](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml)
2. The `✅ Release Readiness Gate` job must show **🟢 RELEASE IS GOVERNANCE-READY**
3. Download the `release-governance-readiness-report` artifact and verify `"governance_ready": true`
4. Read `release-proof-summary.md` for check-class pass/fail/skipped counts and assurance-boundary wording for external technical review

### Production-like Validation

Beyond the unit/integration test suite, VERITAS includes **production-like validation**
that exercises real subsystems (TrustLog, encryption, governance API, web search
security) through production-equivalent code paths:

```bash
# Run production-like tests (no external deps needed)
make test-production

# Run smoke tests only
make test-smoke

# Full validation including Docker Compose (requires Docker)
make validate
```

Production validation is also available as a **separate CI workflow**
(`production-validation.yml`) triggered manually or on a weekly schedule.
See [`docs/PRODUCTION_VALIDATION.md`](docs/en/validation/production-validation.md) for
the complete strategy, verification matrix, and remaining production risks.

For backend semantics parity scope, see
[`docs/BACKEND_PARITY_COVERAGE.md`](docs/en/validation/backend-parity-coverage.md).

---

## ⚙️ Environment Variables Reference

All environment variables in one place. Set these in `.env` (git-ignored) or your secrets manager.

### Required

| Variable | Description | Example |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `VERITAS_API_KEY` | Backend API authentication key | Random string |
| `VERITAS_API_SECRET` | HMAC signing secret (32+ chars) | Random 64-char hex |
| `VERITAS_ENCRYPTION_KEY` | TrustLog encryption key (base64-encoded 32 bytes) | Use `generate_key()` |

### LLM Provider

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM provider (`openai`, `anthropic`, `google`, `ollama`, `openrouter`) |
| `LLM_MODEL` | `gpt-4.1-mini` | Model name |
| `LLM_POOL_MAX_CONNECTIONS` | `20` | httpx connection pool size |
| `LLM_MAX_RETRIES` | `3` | Retry count with exponential backoff |

### Storage Backends

| Variable | Default | Description |
|---|---|---|
| `VERITAS_MEMORY_BACKEND` | `json` (local) / `postgresql` (Docker) | Memory storage backend (`json` or `postgresql`) |
| `VERITAS_TRUSTLOG_BACKEND` | `jsonl` (local) / `postgresql` (Docker) | TrustLog storage backend (`jsonl` or `postgresql`) |
| `VERITAS_DATABASE_URL` | — | PostgreSQL connection URL (required when using `postgresql` backend) |
| `VERITAS_DB_POOL_MIN_SIZE` | `2` | PostgreSQL connection pool minimum size |
| `VERITAS_DB_POOL_MAX_SIZE` | `10` | PostgreSQL connection pool maximum size |
| `VERITAS_DB_SSLMODE` | `prefer` | PostgreSQL SSL mode (`prefer`, `require`, `verify-full`) |
| `VERITAS_DB_AUTO_MIGRATE` | `false` (local) / `true` (Docker) | Auto-run Alembic migrations on startup |

### Network & CORS

| Variable | Default | Description |
|---|---|---|
| `VERITAS_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS allow-list |
| `VERITAS_API_BASE_URL` | `http://backend:8000` | Frontend BFF → backend URL (server-only) |
| `VERITAS_MAX_REQUEST_BODY_SIZE` | `10485760` (10 MB) | Max request body size |

### Safety & Governance

| Variable | Default | Description |
|---|---|---|
| `VERITAS_ENABLE_DIRECT_FUJI_API` | `0` | Enable `/v1/fuji/validate` endpoint |
| `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER` | `0` (posture: `1` in secure/prod) | Block startup without Vault/KMS |
| `VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER` | `1` | Web search toxicity filter (fail-closed) |
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `0` | Enable Continuation Runtime |
| `VERITAS_CONTINUATION_ENFORCEMENT_MODE` | `observe` | Continuation enforcement mode (`observe`, `advisory`, `enforce`) |

### Policy Signing & Enforcement

| Variable | Default | Description |
|---|---|---|
| `VERITAS_POLICY_VERIFY_KEY` | — | Path to Ed25519 public key PEM file for policy bundle signature verification |
| `VERITAS_POLICY_RUNTIME_ENFORCE` | `0` (posture: `1` in secure/prod) | Enable runtime enforcement of compiled policy decisions (deny/halt/escalate/require_human_review) |
| `VERITAS_POLICY_REQUIRE_ED25519` | `0` | Require Ed25519 signature verification; reject manifests when no key is available |

> **Posture-aware enforcement**: In `secure`/`prod` posture, SHA-256-only (unsigned) policy bundles
> are rejected by the runtime adapter.  Only Ed25519-signed bundles pass verification.
> In `dev`/`staging`, SHA-256 integrity checks are accepted with a warning.
> Governance rollback operations follow the same 4-eyes approval and audit requirements as updates.

### TrustLog & Audit

| Variable | Default | Description |
|---|---|---|
| `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` | `0` (posture: `1` in secure/prod) | Require transparency log anchoring (fail-closed) |
| `VERITAS_TRUSTLOG_WORM_HARD_FAIL` | `0` (posture: `1` in secure/prod) | WORM mirror write failure raises error |
| `VERITAS_TRUSTLOG_MIRROR_BACKEND` | `local` | TrustLog mirror backend (`local` or `s3_object_lock`) |
| `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` | — | Local append mirror destination path (used when backend is `local`) |
| `VERITAS_TRUSTLOG_S3_BUCKET` | — | S3 bucket name for TrustLog mirror writes (`s3_object_lock` backend) |
| `VERITAS_TRUSTLOG_S3_PREFIX` | — | S3 object key prefix for append-only TrustLog objects |
| `VERITAS_TRUSTLOG_ANCHOR_BACKEND` | `local` | TrustLog anchor backend (`local` or `noop`) |
| `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` | — | Local transparency anchor path (required when anchor backend is `local` and transparency is required) |
| `VERITAS_TRUSTLOG_S3_REGION` | — | AWS region override for S3 client |
| `VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE` | — | Object Lock mode (`GOVERNANCE` or `COMPLIANCE`) |
| `VERITAS_TRUSTLOG_S3_RETENTION_DAYS` | — | Retention period in days for S3 Object Lock |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE` | `0` | Enable remote S3 mirror verification during TrustLog verification |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT` | `0` | Strict mirror verification: fail on missing receipts (legacy entries) and retention gaps |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_REQUIRE_LEGAL_HOLD` | `0` | Require S3 Object Legal Hold (`ON`) when remote mirror verification is enabled |
| `VERITAS_TRUSTLOG_SIGNER_BACKEND` | `file` | TrustLog signer backend (`file` or `aws_kms`) |
| `VERITAS_TRUSTLOG_KMS_KEY_ID` | — | AWS KMS key id/ARN (required when `VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms`) |

#### TrustLog mirror migration notes

- Existing deployments continue to work with no change because `VERITAS_TRUSTLOG_MIRROR_BACKEND` defaults to `local` and keeps `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` behavior.
- To migrate to S3 Object Lock, set `VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock` and provide at minimum `VERITAS_TRUSTLOG_S3_BUCKET` (plus optional prefix/region/retention settings).
- `VERITAS_TRUSTLOG_WORM_HARD_FAIL` semantics are unchanged and apply to both backends.
- In `secure`/`prod`, the startup validator requires backends with the `immutable_retention` capability. The current implementation satisfying this is `s3_object_lock`; both `VERITAS_TRUSTLOG_S3_BUCKET` and `VERITAS_TRUSTLOG_S3_PREFIX` must be set.

#### TrustLog mirror verification modes

- **Offline mode (default)**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE=0` validates receipt schema only and keeps legacy compatibility.
- **Remote mode**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE=1` performs S3-backed checks for `s3_object_lock` receipts:
  - object existence (`Bucket` + `Key`)
  - `version_id` match (when receipt has `version_id`)
  - `etag` match (when receipt has `etag`)
  - retention state (when receipt records retention metadata)
- **Strict mode**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT=1` is intended for high-assurance/prod verification jobs:
  - fails entries with missing mirror receipts (`mirror_receipt_missing`)
  - fails retention verification gaps (`mirror_retention_missing`)
  - can break verification for old ledgers created before receipt support.
- **Legal hold enforcement**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_REQUIRE_LEGAL_HOLD=1` additionally requires object legal hold to be `ON` (`mirror_legal_hold_missing`).

> Security caveat: remote verification depends on live AWS API access and IAM permissions (`s3:HeadObject`, `s3:GetObjectRetention`, `s3:GetObjectLegalHold`). Use least privilege and isolate verifier credentials.

### Replay

| Variable | Default | Description |
|---|---|---|
| `VERITAS_REPLAY_STRICT` | `0` (posture: `1` in secure/prod) | Enforce deterministic replay settings |
| `VERITAS_REPLAY_REQUIRE_MODEL_VERSION` | `1` | Reject snapshots without model_version |

### Runtime

| Variable | Default | Description |
|---|---|---|
| `VERITAS_POSTURE` | `dev` | Runtime posture (`dev`/`staging`/`secure`/`prod`). See [Runtime Posture Guarantees](#-runtime-posture-guarantees). |
| `VERITAS_RUNTIME_ROOT` | `runtime/` | Root directory for runtime data |
| `VERITAS_RUNTIME_NAMESPACE` | `dev` | Runtime namespace (`dev`/`test`/`demo`/`prod`) |

> See [`.env.example`](.env.example) for a complete template.

---

## 🔐 Security Notes (Important)

> [!WARNING]
> VERITAS is designed to fail closed, but **safe-by-default does not mean safe-without-configuration**. Before any beta deployment, verify secrets handling, encryption keys, WORM/transparency settings, and network exposure in your own environment.

**Key beta-era security warnings**
- Do **not** expose the backend with placeholder secrets such as `VERITAS_API_SECRET=change-me`.
- TrustLog encryption is mandatory in secure mode; missing `VERITAS_ENCRYPTION_KEY` will break writes by design rather than silently downgrading security.
- Treat legacy pickle migration in MemoryOS as a temporary migration-only path because deserialization pathways are high risk.
- Review BFF/server routing carefully; leaking internal API topology via public `NEXT_PUBLIC_*` variables weakens the intended boundary.

### Credential and key management

- **API keys**: Avoid exporting secrets directly in shell history where possible. Prefer
  `.env` files (git-ignored) or secret managers and inject them at runtime. Rotate keys
  regularly and limit scope/permissions.
- **Never use placeholder or short secrets**: `VERITAS_API_SECRET` should be a long,
  random value (32+ chars recommended). Placeholder or short secrets can effectively
  disable or weaken HMAC protection.

### API and browser-facing protections

- **CORS safety**: avoid wildcard origins (`*`) when `allow_credentials` is enabled.
  Configure explicit trusted origins only via `VERITAS_CORS_ALLOW_ORIGINS`.
- **Content Security Policy (CSP)**: the frontend middleware injects per-request nonce-based CSP headers. `connect-src 'self'` restricts XHR/fetch to same origin.
- **BFF session cookie**: `__veritas_bff` is httpOnly, Secure, SameSite=strict in production. Browser never sees API credentials.
- **Security headers**: HSTS (1-year, preload), X-Frame-Options DENY, X-Content-Type-Options nosniff, Permissions-Policy (camera/mic/geo disabled).
- **Rate limiting & auth failure tracking**: per-key rate limits with exponential backoff on repeated auth failures.
- **Nonce replay protection**: critical operations protected by HMAC-signed nonces with TTL cleanup.
- **Request body size limit**: configurable via `VERITAS_MAX_REQUEST_BODY_SIZE` (default 10 MB).

### Data safety and persistence

- **TrustLog data**: TrustLog is **encrypted by default** (secure-by-default). All
  entries are automatically redacted for PII/secrets and encrypted before persistence.
  `VERITAS_ENCRYPTION_KEY` must be set; without it, writes fail.
- **Automatic PII/secret redaction**: Email, phone, address, API keys, bearer tokens,
  and secret-like strings are masked before storage — no manual `redact()` call required.
- **Encryption at rest (mandatory)**: Set `VERITAS_ENCRYPTION_KEY` (base64-encoded
  32-byte key). Use `generate_key()` to create one. Store keys in a vault/KMS, never in
  source control.
- **Operational logs are excluded from Git**: runtime logs (for example,
  `runtime/<namespace>/.../*.jsonl`) are ignored via `.gitignore`; anonymized samples live
  under `veritas_os/sample_data/memory/`.
- **Runtime namespaces are separated by purpose**: default local paths are
  `runtime/dev`, `runtime/test`, `runtime/demo`, `runtime/prod`. You can override with
  `VERITAS_RUNTIME_ROOT` and `VERITAS_RUNTIME_NAMESPACE`.
- **Fresh-clone cleanup command**: use
  `python scripts/reset_repo_runtime.py --dry-run` and
  `python scripts/reset_repo_runtime.py --apply` to remove generated runtime data.
  See also `docs/ja/operations/runtime-data-policy.md`.

### Fail-closed safety pipeline

- **FUJI Gate fail-closed**: all safety judgment exceptions return `status=rejected`, `risk=1.0`. No silent pass-through on error.
- **Governance boundary guard**: `/v1/fuji/validate` returns 403 by default — explicit opt-in required (`VERITAS_ENABLE_DIRECT_FUJI_API=1`).
- **4-eyes approval**: governance policy updates require 2 distinct approvers (no duplicates, enabled by default).
- **RBAC/ABAC**: `require_governance_access` guard on governance management endpoints with role + tenant verification.
- **External secret manager enforcement**: `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1` blocks startup without Vault/KMS integration.
- **Web search toxicity filter**: retrieval poisoning / prompt injection heuristics with NFKC normalization, URL decode, base64 decode, and leet-speak detection. Enabled by default (fail-closed); disable with `VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER=0`.

### Migration safety

- **Legacy pickle migration is risky**: if you enable legacy pickle migration for
  MemoryOS, treat it as a short-lived migration path and disable it afterward.
  Legacy pickle/joblib loading is blocked at runtime to prevent RCE.

---

## 🗺️ Roadmap (Near-Term)

**Already delivered** (previously listed as roadmap items):
- ✅ CI (GitHub Actions): three-tier validation model with pytest + coverage + artifact reports
- ✅ Security hardening: input validation, secret/log hygiene, runtime posture system
- ✅ Policy-as-Code: YAML/JSON → IR → compiled rules with Ed25519-signed bundles and auto-generated tests
- ✅ Multi-provider LLM: OpenAI (production), Anthropic/Google (planned), Ollama/OpenRouter (experimental)
- ✅ PostgreSQL storage backend: pluggable backend for MemoryOS and TrustLog with Alembic migrations, advisory-lock chain serialization, and full parity test suite (195+ tests). Includes JSONL → PostgreSQL import procedure, smoke/release validation integration, and legacy path cleanup. See [`docs/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md).
- ✅ PostgreSQL production hardening: contention tests (25 tests), pool/activity metrics (28 tests), backup/restore/recovery drill scripts and tests (31 tests). See [`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md).
- ✅ Continuation Runtime (Phase-1): chain-level continuation observation layer with snapshot/receipt/enforcement event architecture. See `docs/architecture/continuation_runtime_adr.md`.
- ✅ Governance artifact signing: Ed25519-signed policy bundles, runtime signature verification, governance identity in decision outputs. See [`docs/governance_artifact_lifecycle.md`](docs/en/governance/governance-artifact-lifecycle.md).
- ✅ S3 Object Lock TrustLog mirror: WORM-compliant mirror backend with retention, legal hold, and remote verification. See [`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md).

**Next milestones**:
- Promote Anthropic / Google LLM providers to production tier
- Automatic coverage badge update from CI artifacts
- pgvector integration for MemoryOS vector similarity search
- Phased move from mono-repo licensing (Plan B) to multi-repo split (Plan A)
- Continuation Runtime Phase-2 enforcement graduation from advisory to enforce-by-default in secure/prod posture

---

## 📄 License

This repository is a **multi-license repository** with clear directory scope.

> 日本語補助: このリポジトリは「Coreはプロプライエタリ」「Interfaceはオープン」の二層ライセンスです。

### License matrix (scope by directory)

| Scope | License | Commercial use | Redistribution | Notes |
|---|---|---|---|---|
| Default (entire repo unless overridden) | VERITAS Core Proprietary EULA (`/LICENSE`) | Contract required | Not permitted without written permission | Includes Core decision logic and pipeline |
| `spec/` | MIT (`/spec/LICENSE`) | Permitted | Permitted | Open interface artifacts |
| `sdk/` | MIT (`/sdk/LICENSE`) | Permitted | Permitted | SDK interface layer |
| `cli/` | MIT (`/cli/LICENSE`) | Permitted | Permitted | CLI interface layer |
| `policies/examples/` | MIT (`/policies/examples/LICENSE`) | Permitted | Permitted | Policy templates/examples |

### Core abuse-prevention restrictions (high level)

Under the Core Proprietary EULA, you may not:

- provide Core (or substantially similar functionality) as a competing managed service;
- bypass license keys, metering, or other technical protection controls;
- remove copyright, attribution, proprietary notice, or trademark markings;
- redistribute Core or use Core for commercial production use without a commercial agreement.

See [`LICENSE`](LICENSE), [`TRADEMARKS`](TRADEMARKS), and [`NOTICE`](NOTICE).

### Transition note for existing users

The current structure formalizes existing intent into a clearer two-tier model:

- Core remains proprietary by default.
- Interface assets are explicitly open-licensed by directory.
- No Core logic (Planner/Kernel/FUJI/TrustLog pipeline internals) is open-sourced by this change.

### Roadmap: phased move from mono-repo licensing (Plan B) to multi-repo split (Plan A)

Phase 1 (current):
- Directory-scoped licensing in this mono-repo (Core proprietary + interface MIT)

Phase 2 (upcoming):
- `veritas-spec` (OpenAPI/schema)
- `veritas-sdk-python`, `veritas-sdk-js`
- `veritas-cli`
- `veritas-policy-templates`
- Keep `veritas_os` focused on proprietary Core only

For academic use, please cite the Zenodo DOI.

---

## 🤝 Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines, including:

- Repository license model (Core is proprietary; interfaces are MIT)
- Development setup and coding standards
- Pull request workflow and review process
- Security vulnerability reporting via [`SECURITY.md`](SECURITY.md)

---

## 📝 Citation (BibTeX)

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Auditable Decision OS for LLM Agents},
  year   = {2025},
  doi    = {10.5281/zenodo.17838349},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

---

## 📞 Contact

* Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
