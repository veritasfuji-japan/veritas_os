# VERITAS OS Reviewer Entry Point

## Purpose

This document is the first review entry point for external reviewers, enterprise evaluators, investors, and technical due diligence teams who want to understand VERITAS OS before reading the full repository.

It is designed to clarify current value, implemented scope, proof assets, validation flow, and explicit boundaries/non-claims.

This entry point is organized around the current enterprise review path: business value, implemented scope, one-day evidence, provider/compliance boundaries, and technical appendices.

## 10-minute review path

1. [Enterprise Value Brief](en/positioning/enterprise-value-brief.md) — one-page business/investor overview.
2. [README](../README.md) — core product definition and repository entry map.
3. [Current Implementation Matrix](en/validation/current-implementation-matrix.md) — current implementation facts vs roadmap.
4. [Lara / PromptLedger Static Review Response Matrix](en/validation/lara-promptledger-static-review-response.md) — reviewer-facing map from static review findings to implemented repository responses, with audit/certification caveats.
5. [Operational Readiness Runbook](en/operations/operational-readiness-runbook.md) — release evidence commands, staged readiness report interpretation, and what compose/live subreports do and do not prove.
6. [One-Day PoC Evidence Pack](en/poc/one-day-poc-evidence-pack.md) — what reviewers should inspect, collect, and treat as success/failure evidence in a One-Day PoC.
7. [One-Day PoC Operator Runbook](en/poc/one-day-poc-operator-runbook.md) — how operators prepare, collect, package, and hand off PoC evidence.
8. [One-Day PoC Reviewer Handoff Template](en/poc/one-day-poc-reviewer-handoff-template.md) — submit-ready handoff format for PoC results.
9. [Release Evidence Reviewer Handoff Template](en/validation/release-evidence-reviewer-handoff-template.md) — submit-ready format for release evidence, staged readiness interpretation, subreport presence/absence, and reviewer acknowledgement.
10. [Provider Support Matrix](en/operations/provider-support-matrix.md) — provider tiers, support boundaries, and non-claims.
11. [Public Positioning](en/positioning/public-positioning.md) — conservative positioning and legal/compliance boundary statements.

## 30-minute technical review path

1. [Enterprise Value Brief](en/positioning/enterprise-value-brief.md)
2. [Current Implementation Matrix](en/validation/current-implementation-matrix.md)
3. [Operational Readiness Runbook](en/operations/operational-readiness-runbook.md)
4. [Lara / PromptLedger Static Review Response Matrix](en/validation/lara-promptledger-static-review-response.md)
5. [Production Validation](en/validation/production-validation.md)
6. [Regulated Action Governance Proof Pack](en/validation/regulated-action-governance-proof-pack.md)
7. [One-Day PoC Evidence Pack](en/poc/one-day-poc-evidence-pack.md)
8. [One-Day PoC Operator Runbook](en/poc/one-day-poc-operator-runbook.md)
9. [One-Day PoC Reviewer Handoff Template](en/poc/one-day-poc-reviewer-handoff-template.md)
10. [One-Day PoC Reviewer Pack](en/poc/one-day-poc-reviewer-pack.md)
11. [One-Day PoC Performance Report](en/poc/one-day-poc-performance-report.md)
12. [Type Safety Baseline](en/operations/type-safety-baseline.md)
13. [Maintainer Handoff](en/operations/maintainer-handoff.md)
14. [Release Evidence Reviewer Handoff Template](en/validation/release-evidence-reviewer-handoff-template.md)
15. [Provider Support Matrix](en/operations/provider-support-matrix.md)
16. [Regulated Action Governance Kernel](en/architecture/regulated-action-governance-kernel.md)
17. [Bind Boundary Governance Artifacts](en/architecture/bind-boundary-governance-artifacts.md)

## What VERITAS OS is

VERITAS OS is a Decision Governance and Bind-Boundary Control Plane for AI agents. It is designed to make AI-agent decisions reviewable, traceable, replayable, auditable, and enforceable before real-world effect.

Key reviewer concepts:

- Decision governance for regulated/high-impact action paths.
- Bind-boundary control before real-world side effects.
- Authority Evidence for operator and reviewer traceability.
- BindReceipt / BindSummary artifacts for inspection and replay context.
- Fail-closed behavior as the default safety posture.
- Operator-facing review artifacts for governance and PoC validation.

## What to verify first

| Review question | Primary source | What to check |
|---|---|---|
| What problem does VERITAS solve? | [Enterprise Value Brief](en/positioning/enterprise-value-brief.md) | Enterprise value, target users, and priority use cases. |
| What is implemented today? | [Current Implementation Matrix](en/validation/current-implementation-matrix.md) | Clear separation between current facts and roadmap/foundation-only items. |
| What release evidence exists? | [Operational Readiness Runbook](en/operations/operational-readiness-runbook.md), [Production Validation](en/validation/production-validation.md), [Release Evidence Reviewer Handoff Template](en/validation/release-evidence-reviewer-handoff-template.md), [Release Evidence Manifest Template](en/validation/release-evidence-manifest-template.md) | Review validation tiers, staged readiness v2.1 interpretation, `deployment_ready` boundaries, compose/live subreport handling, and handoff expectations. |
| What should reviewers inspect in the One-Day PoC? | [One-Day PoC Evidence Pack](en/poc/one-day-poc-evidence-pack.md) | Evidence checklist, walkthrough scenarios, success/failure criteria, and non-claim boundaries. |
| How should operators prepare and package the PoC evidence? | [One-Day PoC Operator Runbook](en/poc/one-day-poc-operator-runbook.md) | Pre-flight checklist, evidence folder layout, run sequence, redaction notes, and review handoff package. |
| What should be handed to the reviewer after the PoC? | [One-Day PoC Reviewer Handoff Template](en/poc/one-day-poc-reviewer-handoff-template.md) | Submit-ready summary of scope, environment, scenarios, evidence, results, limitations, and open questions. |
| What can be verified in one day? | [One-Day PoC Reviewer Pack](en/poc/one-day-poc-reviewer-pack.md) | Smoke path, generated evidence packet, and validation workflow. |
| Is there performance evidence? | [One-Day PoC Performance Report](en/poc/one-day-poc-performance-report.md) | Local benchmark method, measurement boundaries, and non-SLA language. |
| What are provider boundaries? | [Provider Support Matrix](en/operations/provider-support-matrix.md) | OpenAI production tier, Anthropic planned with offline contract coverage, and explicit boundaries. |
| Are legal/compliance claims bounded? | [Public Positioning](en/positioning/public-positioning.md), [EU AI Act technical documentation](eu_ai_act/technical_documentation.md) | Positioning uses conservative non-certification language and bounded claims. |
| Is there type safety? | [Type Safety Baseline](en/operations/type-safety-baseline.md) | Narrow, practical baseline rather than full-repository strict typing claims. |
| Is handoff possible? | [Maintainer Handoff](en/operations/maintainer-handoff.md) | Maintainer runbook exists; handoff path is documented but risk is not eliminated. |

## Current proof assets

- [Enterprise Value Brief](en/positioning/enterprise-value-brief.md)
- [One-Day PoC Reviewer Pack](en/poc/one-day-poc-reviewer-pack.md)
- [One-Day PoC Evidence Pack](en/poc/one-day-poc-evidence-pack.md)
- [One-Day PoC Operator Runbook](en/poc/one-day-poc-operator-runbook.md)
- [One-Day PoC Reviewer Handoff Template](en/poc/one-day-poc-reviewer-handoff-template.md)
- For the completed external security review remediation matrix, see [External Security Review Remediation Summary](en/security/external-security-remediation-summary.md).
- [One-Day PoC Performance Report](en/poc/one-day-poc-performance-report.md)
- [Sample evidence JSON](en/poc/sample-one-day-poc-evidence.json)
- [Sample evidence Markdown](en/poc/sample-one-day-poc-evidence.md)
- [Current Implementation Matrix](en/validation/current-implementation-matrix.md)
- [Regulated Action Governance Proof Pack](en/validation/regulated-action-governance-proof-pack.md)
- [Operational Readiness Runbook](en/operations/operational-readiness-runbook.md)
- [Production Validation](en/validation/production-validation.md)
- [Release Evidence Reviewer Handoff Template](en/validation/release-evidence-reviewer-handoff-template.md)
- Checksums file path: `release-artifacts/release-evidence-checksums.sha256`
- Release evidence Make targets: `make validate-staged-report`, `make validate-staged-report-with-subreports`, `make prepare-release-evidence-handoff`, `make prepare-release-evidence-manifest`, `make prepare-release-evidence-checksums`, and `make prepare-release-evidence-package`
- [Provider Support Matrix](en/operations/provider-support-matrix.md)
- [Type Safety Baseline](en/operations/type-safety-baseline.md)
- [Maintainer Handoff Runbook](en/operations/maintainer-handoff.md)
- [Public Positioning](en/positioning/public-positioning.md)
- [AML/KYC regulated action path](en/use-cases/aml-kyc-regulated-action-path.md)
- Anthropic provider contract test path: `veritas_os/tests/test_llm_client_anthropic_contract.py`

## Recommended validation commands

Run docs and reviewer-path checks first:

```bash
python -m scripts.quality.check_bilingual_docs
pytest -q veritas_os/tests/test_enterprise_value_brief_docs.py
pytest -q veritas_os/tests/test_docs_poc_samples.py
pytest -q veritas_os/tests/test_one_day_poc_evidence_pack_docs.py
pytest -q veritas_os/tests/test_one_day_poc_operator_runbook_docs.py
pytest -q veritas_os/tests/test_one_day_poc_reviewer_handoff_template_docs.py
pytest -q veritas_os/tests/test_provider_support_matrix_docs.py
pytest -q veritas_os/tests/test_type_safety_baseline.py
pytest -q veritas_os/tests/test_maintainer_handoff_docs.py
pytest -q veritas_os/tests/test_llm_client_anthropic_contract.py
pytest -q veritas_os/tests/test_reviewer_entrypoint_current_path.py
pytest -q veritas_os/tests/test_release_evidence_reviewer_handoff_template_docs.py

# Release evidence / staged readiness path
python scripts/quality/check_operational_docs_consistency.py
pytest -q veritas_os/tests/test_operational_docs_certification_guard.py
pytest -q veritas_os/tests/test_staged_readiness_report.py
pytest -q veritas_os/tests/test_staged_readiness_make_targets.py
make validate-staged-report
make -n validate-staged-report-with-subreports
make prepare-release-evidence-handoff
make prepare-release-evidence-manifest
make prepare-release-evidence-package
make prepare-release-evidence-checksums
```

One-Day PoC command examples (API server required, API key required):

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_smoke.py --json --evidence-json /tmp/veritas_poc_evidence.json --evidence-md /tmp/veritas_poc_evidence.md
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py --runs 10 --warmup 2 --json --out-json /tmp/veritas_poc_benchmark.json --out-md /tmp/veritas_poc_benchmark.md
```

Use the Evidence Pack to decide what to inspect.
Use the Operator Runbook to collect and organize evidence.
Use the Reviewer Handoff Template to summarize and submit the PoC outcome.
These documents do not create a production SLA, third-party certification, customer-environment measurement, or EU AI Act certification.

For release evidence review, inspect the staged readiness report path. `make validate-staged-report` generates the no-subreport staged report. `make validate-staged-report-with-subreports` attaches compose/live reports but may require provider secrets, so reviewers can use `make -n validate-staged-report-with-subreports` to inspect the command sequence safely. Run `make prepare-release-evidence-package` for one-command no-subreport package preparation, and `make prepare-release-evidence-checksums` when you need to refresh `release-artifacts/release-evidence-checksums.sha256`.

Boundary notes for PoC commands:

- API server is required for end-to-end PoC execution.
- `VERITAS_API_KEY` is required for authenticated runs.
- Do not print or commit secrets/tokens into logs, docs, or evidence files.

## Current boundaries and non-claims

- Not legal advice.
- Not regulatory approval.
- Not third-party certification.
- Not EU Declaration of Conformity.
- Not CE marking.
- Not production SLA.
- Not 24/7 support.
- Not proof of provider-neutral production readiness.
- Not proof of live bank/healthcare/government integration.
- Not full repository strict typing.
- Not elimination of bus-factor risk.
- Fixture/demo evidence is not live customer integration.
- One-Day PoC evidence is not production audit evidence.
- One-Day PoC handoff is not customer-environment verification unless explicitly run and documented in that environment.
- Local/configured PoC output is not proof of production latency, production availability, or third-party certification.
- Provider latency/cost is not measured unless providers are intentionally enabled and separately recorded.
- Staged readiness and release evidence reports support review, but are not production certification, third-party certification, or customer-environment verification by themselves.

## Provider and model boundary

OpenAI is the current production-tier provider. Anthropic and Google remain Planned. Ollama/OpenRouter-style paths remain Experimental unless code and docs state otherwise. Anthropic has offline contract coverage, but that coverage does not promote it to production.

## Compliance positioning boundary

VERITAS supports EU AI Act-aligned governance workflows by producing inspectable control and audit evidence. It is not legal certification, conformity assessment, EU Declaration of Conformity, CE marking, or regulatory approval.

## Technical appendix: Observe Mode foundation

Observe Mode material is retained as a foundation/technical appendix path, not the primary enterprise reviewer path.

- `docs/governance/observe_mode_proof_pack.md`
- `docs/governance/observe_mode.md`
- `docs/ui/README_UI.md`
- `/dev/mission-fixture`
- `scripts/validate_governance_observation_fixture.sh`
- `scripts/check_governance_observation.py`
- `scripts/generate_observe_mode_demo_snapshot.py`

Observe Mode boundary reminders:

- Observe Mode runtime is not enabled.
- Production remains fail-closed.
- Demo fixture evidence is not production runtime evidence.

## Reviewer checklist

- [ ] Read Enterprise Value Brief.
- [ ] Read Current Implementation Matrix.
- [ ] Review One-Day PoC Reviewer Pack.
- [ ] Review One-Day PoC Evidence Pack.
- [ ] Use Operator Runbook when preparing or auditing PoC evidence collection.
- [ ] Review completed Reviewer Handoff Template if PoC results are being submitted.
- [ ] Review release evidence commands and staged readiness interpretation.
- [ ] Confirm `deployment_ready` is not being treated as production certification.
- [ ] Confirm compose/live subreports are attached or explicitly absent when reviewing release evidence.
- [ ] Complete or review the Release Evidence Reviewer Handoff Template when submitting release evidence.
- [ ] Generate or inspect evidence packet.
- [ ] Confirm Evidence Packet / Evidence Pack / Handoff Template are not being presented as production audit evidence or certification.
- [ ] Review performance report boundaries.
- [ ] Review provider matrix.
- [ ] Review compliance positioning boundaries.
- [ ] Review type safety baseline.
- [ ] Review maintainer handoff runbook.
- [ ] Confirm non-claims.
- [ ] Record unresolved questions.

## Open questions / limitations

- External security review is still needed.
- Legal review and conformity assessment are not included.
- Production deployment posture must be evaluated per customer environment.
- Live customer integrations are not proven by fixture/demo evidence.
- Provider-neutral production readiness is not proven.
- Type safety is baseline-only, not full-repository strict typing.
- Bus-factor risk remains.
