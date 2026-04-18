# Financial PoC Pack (1-day quickstart, EN)

## Purpose

This quickstart turns the AML/KYC beachhead from "docs" into a
**1-day executable PoC pack** with operator checkpoints and evidence handoff.

What this pack proves in implemented scope:

1. **Fail-closed governance behavior** in `/v1/decide`.
2. **Expected semantics diffing** against fixture baselines.
3. **Quantitative pass/fail/warning summary** for demo and internal go/no-go.
4. **Evidence-readiness path** toward external audit bundle generation.

---

## Who this guide is for

- **Customer-side evaluator**: confirm AML/KYC governance value quickly.
- **Operator**: run and interpret results without guessing hidden assumptions.
- **Investor / sponsor**: understand what is already implemented vs pending.

---

## Scope (single beachhead)

This PoC is intentionally constrained to one beachhead:

- **Beachhead domain**: `aml_kyc`
- **Anchor template**: `aml_kyc_high_risk_country_wire_manual_review`

Representative AML/KYC and adjacent governance cases covered by this pack:

- sanctions partial match must **not** become `proceed`
- source of funds missing must **not** become `APPROVE`
- approval boundary unknown must go to `human_review_required` or `hold`
- high-risk ambiguity must go to human review path
- sufficient evidence should allow `proceed/APPROVE` family
- policy definition missing must go to `POLICY_DEFINITION_REQUIRED` family
- secure/prod controls missing must trigger fail-closed `block`

Reference pack semantics and taxonomy:

- [Financial Governance Templates](financial-governance-templates.md)
- [Required Evidence Taxonomy v0](../governance/required-evidence-taxonomy.md)

---

## Inputs and runner

- PoC question fixture:
  `veritas_os/sample_data/governance/financial_poc_questions.json`
- Runner:
  `scripts/run_financial_poc.py`
- Runtime module:
  `veritas_os/scripts/financial_poc_runner.py`

---

## 1-day PoC quickstart (operator runbook)

### Step 0 — Prepare environment (30-60 min)

1. Start VERITAS OS (Docker Compose recommended from repository root).
2. Confirm backend health:

```bash
curl -s http://localhost:8000/health
```

3. Confirm PoC input fixture exists:

```bash
test -f veritas_os/sample_data/governance/financial_poc_questions.json && echo "fixture_ok"
```

### Step 1 — Dry-run baseline (15 min)

Use dry-run first to validate fixture loading and expected semantics formatting:

```bash
python scripts/run_financial_poc.py \
  --dry-run \
  --output-json veritas_os/scripts/logs/financial_poc_dry_run_report.json
```

### Step 2 — Live governance run (30-60 min)

Run against `/v1/decide` with strict required-evidence mode:

```bash
VERITAS_API_KEY=demo-key \
python scripts/run_financial_poc.py \
  --api-url http://localhost:8000/v1/decide \
  --required-evidence-mode strict \
  --output-json veritas_os/scripts/logs/financial_poc_live_report.json
```

### Step 3 — Operator checkpoint readout (30 min)

Validate that results satisfy minimum demo sign-off:

- `warning_count = 0`
- `fail_count = 0`
- `pass_rate >= 0.90`
- `evaluated_count >= 5`
- anchor case `poc_aml_pep_high_risk_country = pass`

### Step 4 — Evidence readiness checkpoint (30 min)

After pass criteria, move to external handoff preparation:

1. Review bundle and verifier flow:
   [External Audit Readiness](../validation/external-audit-readiness.md)
2. Generate decision/incident/release bundle only for synthetic PoC data.
3. Attach verification report + acceptance checklist before stakeholder sharing.

### Dry-run (no API dependency)

```bash
python scripts/run_financial_poc.py \
  --dry-run \
  --output-json veritas_os/scripts/logs/financial_poc_dry_run_report.json
```

### Live run (`/v1/decide`)

```bash
VERITAS_API_KEY=demo-key \
python scripts/run_financial_poc.py \
  --api-url http://localhost:8000/v1/decide \
  --required-evidence-mode strict \
  --output-json veritas_os/scripts/logs/financial_poc_live_report.json
```

---

## Success criteria (quantified)

Use the criteria in:

- [Financial PoC Success Criteria](financial-poc-success-criteria.md)

At minimum for demo sign-off (quantitative):

- `warning_count = 0`
- `fail_count = 0`
- `pass_rate >= 0.90` (on evaluated, non-warning cases)
- `evaluated_count >= 5`
- anchor case `poc_aml_pep_high_risk_country = pass`

---

## Operator-facing explanation (how to interpret output)

The PoC report is designed for operational triage, not only pass/fail display.

- `summary.outcome`:
  - `pass`: evaluated cases met expected semantics.
  - `warning`: non-fatal mismatches or schema/profile warnings need review.
  - `fail`: one or more required semantics diverged from baseline.
- `mismatch_summary`:
  fast explanation of where semantics diverged (gate decision, action family,
  or evidence keys).
- evidence warnings (`required_evidence_runtime_warnings`):
  highlight taxonomy/profile drift that may still pass functional routing but
  reduce audit confidence.

Operator rule of thumb:

- Do **not** treat a high pass rate as sufficient if evidence warnings persist.
- For AML/KYC beachhead, `proceed` with missing required evidence should be
  treated as blocker-level regression.

---

## Diff semantics and mismatch summary

The runner compares these fields per case:

- `gate_decision`
- `business_decision`
- `next_action`
- `required_evidence`
- `missing_evidence`
- `human_review_required`
- runtime evidence warnings (`required_evidence_runtime_warnings`)

Comparator helper:

- `veritas_os/scripts/expected_semantics_compare.py`
- Used by `veritas_os/scripts/financial_poc_runner.py` for machine-readable diffs
  with gate canonicalization, taxonomy-aware evidence comparison, and next-action
  family fallback. Runner output now also includes `mismatch_summary` for
  faster AML/KYC triage.
  It also surfaces:
  - canonicalized expected/actual evidence deltas (`only_in_expected`,
    `only_in_actual`),
  - unknown key warnings (`top_unknown_keys`), and
  - profile miss warnings (`profile_missing_keys`).

Example mismatch output (JSON excerpt):

```json
{
  "question_id": "poc_cross_border_purpose_unknown",
  "status": "fail",
  "mismatch_count": 2,
  "mismatch_summary": "2 mismatch(es): gate_decision[hold→proceed] | required_evidence[0/2] missing=['transaction_purpose_statement', 'source_of_funds_record'] extra=[]",
  "mismatches": {
    "gate_decision": {
      "expected": "hold",
      "actual": "proceed"
    },
    "required_evidence": {
      "expected": ["transaction_purpose_statement", "source_of_funds_record"],
      "actual": []
    }
  }
}
```

Runner summary now includes:

- `summary.outcome`: `pass` / `warning` / `fail`
- `summary.evaluated`
- `summary.warning_rate`
- `summary.mismatch_field_counts`
- `mismatch_overview` (non-pass cases only; easy triage view)

---

## How this connects to demo and benchmark

1. **3-minute demo script**
   - Use the demo flow for UI walkthrough, then show the runner summary to prove
     reproducibility of governance semantics.
   - Reference: [3-Minute Demo Script](demo-script.md)

2. **Evidence benchmark plan**
   - Feed runner report counts (`pass/fail/warning`) and mismatch artifacts into
     the benchmark narrative for "fail-closed safety" and auditability claims.
   - Reference: [Evidence Benchmark Plan](../../benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md)

---

## Role-based short explanation pointers

- Customer-facing short explanation:
  [AML/KYC short positioning](../positioning/aml-kyc-beachhead-short-positioning.md)
- Investor-facing short explanation:
  [AML/KYC short positioning](../positioning/aml-kyc-beachhead-short-positioning.md)

---

## Security warnings

- Do not send production PII or account identifiers in PoC payloads.
- Avoid exposing API keys in shell history or logs.
- Runner warns when using `http://` in live mode; keep HTTP limited to localhost.
