# Release Evidence Manifest Template

- This manifest summarizes the release evidence package for reviewer navigation.
- It lists expected artifacts, whether they are present, and whether they are required, recommended, conditional, or absent.
- It complements the Release Evidence Reviewer Handoff Template.
- It is not production certification.
- It is not third-party certification.
- It is not customer-environment verification unless the listed evidence was generated in that environment.
- It does not certify legal, regulatory, or compliance status.

## Purpose

Use this template as the package index for release evidence submissions so reviewers can confirm what is present, absent, required, conditional, and intentionally omitted.

## Package summary

- Package date:
- Operator:
- Reviewer / organization:
- Repository:
- Commit SHA:
- Branch or tag:
- Evidence folder:
- Environment type: local / CI / staging / customer-managed
- Manifest status: complete / incomplete / inconclusive
- Handoff file prepared: yes / no
- Checksums file prepared: yes / no
- Package prepared by one-command target: yes / no
- Staged readiness report prepared: yes / no
- Compose report attached: yes / no
- Live provider report attached: yes / no
- Provider secrets configured: yes / no / partial / unknown
- Redaction status:

## Expected artifacts

| Artifact | Expected path | Status | Required level | Notes |
|---|---|---|---|---|
| Release evidence manifest | `release-artifacts/release-evidence-manifest.md` | present / absent | Yes | |
| Reviewer handoff | `release-artifacts/release-evidence-reviewer-handoff.md` | present / absent | Yes | Prepared from the reviewer handoff template |
| Staged readiness JSON | `release-artifacts/staged-readiness-report.json` | present / absent | Yes | |
| Staged readiness text | `release-artifacts/staged-readiness-report.txt` | present / absent | Recommended | |
| Compose validation JSON | `release-artifacts/compose-validation-report.json` | present / absent | Conditional | Required when compose subreport is claimed attached |
| Live provider JSON | `release-artifacts/live-provider-report.json` | present / absent | Conditional | Required when live provider subreport is claimed attached |
| Checksums | `release-artifacts/release-evidence-checksums.sha256` | present / absent | Recommended | SHA256 checksums for present release evidence artifacts |
| Command log |  | present / absent | Recommended | |
| CI status / PR URL |  | present / absent | Recommended | |
| Redaction notes |  | present / absent | Conditional | |
| Reviewer notes |  | present / absent | Recommended | |

## Presence checklist

- [ ] Manifest reviewed
- [ ] Reviewer handoff file prepared
- [ ] Staged readiness JSON present
- [ ] Staged readiness text present or intentionally omitted
- [ ] Compose report attached or explicitly absent
- [ ] Live provider report attached or explicitly absent
- [ ] Checksums file present or intentionally omitted
- [ ] One-command package target used or manual steps documented
- [ ] Command log or CI reference included
- [ ] Redaction notes included when needed
- [ ] Missing artifacts explained
- [ ] Non-claim boundaries reviewed

## Staged readiness files

- Staged readiness JSON path: `release-artifacts/staged-readiness-report.json`
- Staged readiness text path: `release-artifacts/staged-readiness-report.txt`
- `deployment_ready=true` does not by itself prove advisory issues are cleared.

## Compose and live provider files

- Compose report path: `release-artifacts/compose-validation-report.json`
- Live provider report path: `release-artifacts/live-provider-report.json`
- Absent compose/live files are not evidence that those validations ran.
- Live provider validation may require provider secrets.
- If compose/live subreports are claimed attached in the staged readiness report, the corresponding JSON artifact should be present in the package.

## Reviewer handoff file

- Handoff path: `release-artifacts/release-evidence-reviewer-handoff.md`
- Prepare it with `make prepare-release-evidence-handoff`
- The handoff file should be filled in before submitting the package.
- `make prepare-release-evidence-package` prepares the no-subreport release evidence package by running staged readiness generation, handoff preparation, manifest preparation, and checksum generation. Use the with-subreports target separately when compose/live evidence is required and provider secrets are available.
- The manifest indexes the package; the handoff records reviewer-facing interpretation and acknowledgement.

## Command log and CI references

Record command logs and CI/PR references, including at minimum:

```bash
make prepare-release-evidence-manifest
make prepare-release-evidence-handoff
make prepare-release-evidence-package
make prepare-release-evidence-checksums
make validate-staged-report
make -n validate-staged-report-with-subreports
```

## Missing or intentionally absent artifacts

- Artifact:
- Reason absent:
- Impact on review:
- Follow-up owner:
- Target date:

## Redaction notes

- Redacted artifact:
- Reason:
- Reviewer impact:
- Additional disclosure:

## Non-claim boundaries

- Do not claim production certification from this manifest.
- Do not claim third-party certification.
- Checksums help reviewers detect submitted file changes, but are not third-party attestation and are not tamper-proof storage by themselves.
- Do not claim customer-environment verification unless the evidence was generated in that environment and documented.
- Do not claim legal or regulatory approval.
- Do not claim provider health unless live provider validation ran with required secrets and the evidence is attached.
- Do not treat absent compose/live artifacts as proof that those validations ran.
- Do not treat `deployment_ready=true` as proof that advisory issues are cleared.

## Related documents

- [`docs/REVIEWER_ENTRYPOINT.md`](../../REVIEWER_ENTRYPOINT.md)
- [`docs/en/validation/release-evidence-reviewer-handoff-template.md`](release-evidence-reviewer-handoff-template.md)
- [`docs/en/operations/operational-readiness-runbook.md`](../operations/operational-readiness-runbook.md)
- [`docs/en/validation/production-validation.md`](production-validation.md)
- [`docs/en/validation/current-implementation-matrix.md`](current-implementation-matrix.md)
