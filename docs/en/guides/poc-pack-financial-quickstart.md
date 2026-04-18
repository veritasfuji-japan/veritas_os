# Financial PoC Pack (1-day quickstart, EN)

## Purpose

This quickstart turns the financial beachhead PoC from "readable docs" into a
**reproducible, measurable run**.

What this pack proves:

1. **Fail-closed governance behavior** in `/v1/decide`.
2. **Expected semantics diffing** against fixture baselines.
3. **Quantitative pass/fail/warning summary** for demo and benchmark handoff.

---

## Scope (single beachhead)

This PoC is intentionally constrained to one beachhead:

- **Beachhead domain**: `aml_kyc`
- **Anchor template**: `aml_kyc_high_risk_country_wire_manual_review`

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
  --output-json veritas_os/scripts/logs/financial_poc_live_report.json
```

---

## Success criteria (quantified)

Use the criteria in:

- [Financial PoC Success Criteria](financial-poc-success-criteria.md)

At minimum for demo sign-off:

- `warning_count = 0`
- `fail_count = 0`
- `pass_rate >= 0.90` (on evaluated, non-warning cases)

---

## Diff semantics and mismatch summary

The runner compares these fields per case:

- `gate_decision`
- `business_decision`
- `next_action`
- `required_evidence`
- `missing_evidence`
- `human_review_required`

Comparator helper:

- `veritas_os/scripts/expected_semantics_compare.py`
- Used by `veritas_os/scripts/financial_poc_runner.py` for machine-readable diffs
  with gate canonicalization, taxonomy-aware evidence comparison, and next-action
  family fallback. Runner output now also includes `mismatch_summary` for
  faster AML/KYC triage.

Example mismatch output (JSON excerpt):

```json
{
  "question_id": "poc_cross_border_purpose_unknown",
  "status": "fail",
  "mismatch_count": 2,
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

## Security warnings

- Do not send production PII or account identifiers in PoC payloads.
- Avoid exposing API keys in shell history or logs.
- Runner warns when using `http://` in live mode; keep HTTP limited to localhost.
