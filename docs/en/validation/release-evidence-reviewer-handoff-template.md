# Release Evidence Reviewer Handoff Template

- This is a reviewer-facing handoff template for release evidence and staged readiness review.
- It summarizes what was run, what evidence was collected, what passed, what failed, and what remains open.
- It complements the Operational Readiness Runbook and Production Validation documentation.
- It is not production certification.
- It is not third-party certification.
- It is not customer-environment verification unless explicitly run and documented in that environment.
- It does not certify legal, regulatory, or compliance status.
- Live provider evidence depends on configured provider secrets and separately recorded execution.

## Purpose

Use this template to submit release evidence for external review with clear scope, artifacts, command history, boundaries, and unresolved items.

## Handoff summary

- Review date:
- Operator:
- Reviewer / organization:
- Repository:
- Commit SHA:
- Branch or tag:
- Environment type: local / CI / staging / customer-managed
- Evidence folder:
- Overall release evidence status: pass / fail / inconclusive
- Compose subreport attached: yes / no
- Live provider subreport attached: yes / no
- Provider secrets configured: yes / no / partial / unknown
- Redaction status:

## Release evidence scope

- [ ] Operational Readiness Runbook reviewed
- [ ] Production Validation documentation reviewed
- [ ] Staged readiness report generated or inspected
- [ ] `deployment_ready` interpretation reviewed
- [ ] Compose validation report attached or explicitly absent
- [ ] Live provider report attached or explicitly absent
- [ ] Advisory findings reviewed
- [ ] Non-claim boundaries explained
- [ ] Open questions documented

## Environment and commit

- Repository URL:
- Commit SHA:
- Branch/tag:
- Runtime profile (local/CI/staging/customer-managed):
- Date/time window:
- Operator notes:

## Commands run

Run and record the commands below as part of release evidence packaging and review handoff:

```bash
python scripts/quality/check_operational_docs_consistency.py
pytest -q veritas_os/tests/test_operational_docs_certification_guard.py
pytest -q veritas_os/tests/test_staged_readiness_report.py
pytest -q veritas_os/tests/test_staged_readiness_make_targets.py
make validate-staged-report
make -n validate-staged-report-with-subreports
make prepare-release-evidence-handoff
make prepare-release-evidence-manifest
```

`make validate-staged-report` generates the no-subreport staged report. `make validate-staged-report-with-subreports` attaches compose/live reports but may require provider secrets, so `make -n validate-staged-report-with-subreports` can be used to inspect the command sequence safely before running the secrets-required path. `make prepare-release-evidence-handoff` copies this template to `release-artifacts/release-evidence-reviewer-handoff.md` so operators can fill in the handoff file alongside generated staged readiness artifacts. `make prepare-release-evidence-manifest` copies the manifest template to `release-artifacts/release-evidence-manifest.md` so reviewers can navigate the submitted release evidence package.

## Evidence artifacts provided

| Evidence item | File/path | Required? | Notes |
|---|---|---|---|
| Staged readiness JSON | `release-artifacts/staged-readiness-report.json` | Yes | |
| Staged readiness text | `release-artifacts/staged-readiness-report.txt` | Recommended | |
| Compose validation JSON | `release-artifacts/compose-validation-report.json` | Conditional | Required when compose subreport is claimed attached |
| Live provider JSON | `release-artifacts/live-provider-report.json` | Conditional | Required when live provider subreport is claimed attached |
| Command log |  | Recommended | |
| CI status / PR URL |  | Recommended | |
| Redaction notes |  | Conditional | |
| Reviewer notes |  | Yes | |

## Staged readiness interpretation

- `deployment_ready=true` means blocking governance checks passed and no attached compose report failed.
- `deployment_ready=true` does not mean compose validation was attached; check `compose_validation`.
- `deployment_ready=true` does not mean live providers were checked; check `live_provider_validation`.
- Advisory failures are non-blocking but require reviewer/operator review.
- The report is evidence for release review, not production certification.

## Compose and live provider subreports

- `compose_validation` present / absent:
- `live_provider_validation` present / absent:
- Compose result:
- Live provider result:
- Missing artifact explanation:
- Secrets configured:
- Reviewer note:

Absent compose/live subreports are treated as not failed by the staged report generator, but absence is not evidence that those validations ran.
Live provider validation may require provider secrets and may skip checks when secrets are absent.

## Advisory findings review

- `overall_readiness.advisory_issue_count`:
- `overall_readiness.advisory_issues`:
- `governance.advisory_failure_labels`:
- Reviewer decision:
- Follow-up required:

## Results summary

- Overall status: pass / fail / inconclusive
- Governance blocking checks:
- Compose validation:
- Live provider validation:
- Advisory findings:
- Evidence completeness:
- Reviewer confidence:
- Follow-up required:

## Known limitations

- Evidence reflects the documented environment and execution window only.
- Missing provider secrets can limit live validation scope.
- Advisory findings may remain open while blocking checks pass.

## Non-claim boundaries

- Do not claim production certification from this handoff.
- Do not claim third-party certification.
- Do not claim customer-environment verification unless the evidence was actually generated in that environment and documented.
- Do not claim legal or regulatory approval.
- Do not claim provider health unless live provider validation was run with required secrets and evidence is attached.
- Do not treat `deployment_ready=true` as proof that all advisory issues are cleared.
- Do not treat absent compose/live subreports as proof that those validations ran.

## Open questions and follow-up

- Open question:
- Owner:
- Target date:
- Required artifact update:

## Reviewer acknowledgement

- Reviewer name:
- Organization:
- Date:
- Acknowledgement:
  - [ ] I reviewed the provided release evidence.
  - [ ] I understand the stated non-claim boundaries.
  - [ ] I understand `deployment_ready` is not production certification.
  - [ ] I understand absent compose/live subreports are not evidence that those validations ran.

## Related documents

- [`docs/REVIEWER_ENTRYPOINT.md`](../../REVIEWER_ENTRYPOINT.md)
- [`docs/en/validation/release-evidence-manifest-template.md`](release-evidence-manifest-template.md)
- [`docs/en/operations/operational-readiness-runbook.md`](../operations/operational-readiness-runbook.md)
- [`docs/en/validation/production-validation.md`](production-validation.md)
- [`docs/en/validation/current-implementation-matrix.md`](current-implementation-matrix.md)
