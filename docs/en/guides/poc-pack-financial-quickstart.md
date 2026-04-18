# Financial PoC Pack (1-day quickstart, EN)

## Purpose

This quickstart turns the AML/KYC beachhead from "docs" into a
**pilot-ready package** with operator checkpoints, evaluator criteria,
and evidence handoff.

What this package proves in implemented scope:

1. **Fail-closed governance behavior** in `/v1/decide`.
2. **Expected semantics diffing** against fixture baselines.
3. **Quantitative pass/fail/warning summary** for pilot go/no-go.
4. **Evidence-readiness handoff path** toward external review bundle generation.

---

## Who this guide is for

- **Customer-side evaluator**: confirm AML/KYC governance value quickly.
- **Operator**: run and interpret results without hidden assumptions.
- **Internal sponsor**: approve pilot readiness with explicit boundaries.

---

## Scope (single beachhead)

This package is intentionally constrained to one beachhead:

- **Beachhead domain**: `aml_kyc`
- **Anchor template**: `aml_kyc_high_risk_country_wire_manual_review`

Representative AML/KYC contracts covered by this package:

- sanctions partial match must **not** become `proceed`
- source of funds missing must **not** become `APPROVE`
- policy definition missing must route to `POLICY_DEFINITION_REQUIRED` family
- sufficient evidence low-risk path may route to `proceed/APPROVE` family
- secure/prod controls missing in secure posture must fail-closed to `block`

Reference semantics and taxonomy:

- [Financial Governance Templates](financial-governance-templates.md)
- [Required Evidence Taxonomy v0](../governance/required-evidence-taxonomy.md)

---

## Pilot package artifacts

### 1) Pilot checklist

- [AML/KYC Pilot Checklist](aml-kyc-pilot-checklist.md)

### 2) Operator runbook

- [AML/KYC Operator Runbook](aml-kyc-operator-runbook.md)

### 3) Canned synthetic sample cases

- `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`

### 4) Expected evidence bundle examples

- `veritas_os/sample_data/governance/aml_kyc_expected_evidence_bundle_examples.json`

### 5) Red-team / failure scenarios

- `veritas_os/sample_data/governance/aml_kyc_failure_scenarios.json`

### 6) Acceptance criteria summary

- [Financial PoC Success Criteria](financial-poc-success-criteria.md)

### 7) Customer handoff path

- [AML/KYC Customer Handoff Path](aml-kyc-customer-handoff-path.md)

### 8) Security / privacy boundaries

- [AML/KYC Pilot Checklist](aml-kyc-pilot-checklist.md#security-and-privacy-boundaries-must-not-cross)

---

## Inputs and runner

- Pilot fixture:
  `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`
- Runner:
  `scripts/run_financial_poc.py`
- Runtime module:
  `veritas_os/scripts/financial_poc_runner.py`

---

## 1-day pilot quickstart (operator path)

### Step 0 — Prepare environment (30-60 min)

1. Start VERITAS OS (Docker Compose recommended from repository root).
2. Confirm backend health:

```bash
curl -s http://localhost:8000/health
```

3. Confirm pilot fixture exists:

```bash
test -f veritas_os/sample_data/governance/aml_kyc_pilot_cases.json && echo "fixture_ok"
```

### Step 1 — Dry-run baseline (15 min)

```bash
python scripts/run_financial_poc.py \
  --input veritas_os/sample_data/governance/aml_kyc_pilot_cases.json \
  --dry-run \
  --output-json veritas_os/scripts/logs/aml_kyc_pilot_dry_run_report.json
```

### Step 2 — Live governance run (30-60 min)

```bash
VERITAS_API_KEY=demo-key \
python scripts/run_financial_poc.py \
  --input veritas_os/sample_data/governance/aml_kyc_pilot_cases.json \
  --api-url http://localhost:8000/v1/decide \
  --required-evidence-mode strict \
  --output-json veritas_os/scripts/logs/aml_kyc_pilot_live_report.json
```

### Step 3 — Acceptance checkpoint (30 min)

Validate minimum pilot sign-off:

- `summary.counts.warning = 0`
- `summary.counts.fail = 0`
- `summary.pass_rate >= 0.90`
- `summary.evaluated >= 5`
- anchor case `pilot_aml_kyc_anchor_high_risk_country = pass`

### Step 4 — Evidence handoff checkpoint (30 min)

1. Review handoff flow:
   [AML/KYC Customer Handoff Path](aml-kyc-customer-handoff-path.md)
2. Review external bundle contract:
   [External Audit Readiness](../validation/external-audit-readiness.md)
3. Share synthetic-only artifacts with acceptance summary.

---

## Operator-facing output interpretation

- `summary.outcome`:
  - `pass`: all evaluated cases matched expected semantics.
  - `warning`: runtime instability or bounded warning state exists.
  - `fail`: one or more required semantics diverged from baseline.
- `mismatch_overview`:
  concise triage view for non-pass cases.
- `required_evidence_runtime_warnings`:
  taxonomy/profile drift signals that may reduce audit confidence.

Operator rule of thumb:

- Do **not** treat pass rate alone as sufficient when warnings remain.
- Treat unexpected `proceed/APPROVE` in ambiguity cases as blocker-level.

---

## Security warnings

- Do not send production PII or account identifiers in pilot payloads.
- Avoid exposing API keys in shell history or logs.
- Keep HTTP endpoints limited to localhost rehearsal environments.
- This package is governance routing + evidence posture only, not legal advice.
