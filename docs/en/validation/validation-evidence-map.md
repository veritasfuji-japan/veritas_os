# Validation Evidence Map

**Objective:** Map implemented validation layers to concrete repository artifacts.

## Layered evidence model

### L1 — Contract-level semantics

- Decision semantics public contract with canonical values and forbidden combinations.
- Required evidence taxonomy/profile behavior (`warn` / `strict`) for AML/KYC path.

References:
- [Decision Semantics Contract](../architecture/decision-semantics.md)
- [Required Evidence Taxonomy](../governance/required-evidence-taxonomy.md)

### L2 — Runtime implementation path

- Decision response derivation and gate semantics canonicalization are implemented in backend modules.
- Governance backend selection path implemented via factory/config/repository split.
- Audit evidence generation/verification modules are present.

Representative code paths:
- `veritas_os/core/decision_semantics.py`
- `veritas_os/core/pipeline/pipeline_response.py`
- `veritas_os/governance/factory.py`
- `veritas_os/audit/evidence_bundle.py`
- `veritas_os/audit/trustlog_verify.py`

### L3 — Test and parity coverage layer

- Backend parity and production validation strategy are documented with CI/live validation posture.
- Governance/trustlog/evidence related tests exist in repository test suites.

References:
- [Backend Parity Coverage](backend-parity-coverage.md)
- [Production Validation](production-validation.md)

### L4 — Audit handoff layer

- Evidence bundle contract (`decision_record`, `acceptance_checklist`) is documented.
- External audit readiness path includes verifier and timestamp-anchoring options.

Reference:
- [External Audit Readiness](external-audit-readiness.md)

---

## Evidence request mapping for reviewers

| Reviewer question | Start artifact |
|---|---|
| Is gate semantics stable and bounded? | `docs/en/architecture/decision-semantics.md` |
| Is required evidence contract explicit? | `docs/en/governance/required-evidence-taxonomy.md` |
| Is external bundle handoff defined? | `docs/en/validation/external-audit-readiness.md` |
| Is production validation posture documented with boundaries? | `docs/en/validation/production-validation.md` + `docs/en/operations/postgresql-production-guide.md` |
| Is AML/KYC pilot evidence path runnable? | `docs/en/guides/poc-pack-financial-quickstart.md` + `docs/en/guides/aml-kyc-pilot-checklist.md` |

