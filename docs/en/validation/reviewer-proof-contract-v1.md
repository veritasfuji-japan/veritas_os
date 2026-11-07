# Reviewer Proof Contract v1 — controlled Decision-to-Effect

**Purpose:** add narrowly scoped, fail-closed *evidence consistency* checks
to the existing controlled E2E, not reimplement its enforcement logic.

## What is reused

- Existing real TLS/PostgreSQL controlled E2E test.
- Existing checkout-bound proof provenance helper.
- VERITAS canonical JSON digest helper.
- Native authorization-consumption, reconciliation-archive and receipt-bundle
  Pydantic models (not redefined in this validator).
- Existing CI proof assertions and migration-head comparison.

## What is added

- Contract: contracts/reviewer-proof-contract-v1.json
- Reviewer gate: scripts/validation/verify_reviewer_proof_contract_v1.py
- Mutation tests: tests/validation/test_reviewer_proof_contract_v1.py

The contract is pinned by a canonical JSON digest in the verifier. A change
to ANY contract field (including scenario expectations, exclusions or required
predicates) fails until explicitly reviewed and updated. **An in-repository
digest is not an independent trust root:** external reviewers must obtain an
approved commit/contract digest through an independent channel.

The validator checks the existing normal and fault cases:

1. All 18 mandatory proof predicates, required nonproduction claims and exact
   scenario expectations.
2. Existing canonical evidence/report hashes and actual Git checkout
   provenance.
3. IDs linking decision, promotion, authorization, consumption, reconciliation
   operation, BindReceipt and OutcomeReceipt.
4. Native consumption hash/ID, receipt-bundle hash and reconciliation digest.

The negative tests deliberately rehash altered artifacts to show that simple
file self-hash agreement alone cannot bypass these structural assertions.

The success label is PASS_BOUNDED_CONSISTENCY_ONLY. The self-produced
controlled E2E is internally consistent under the pinned contract. The output
field `producer_reported_pass_predicate_count` counts the 18 PASS predicates
**as reported by the producer**, not independent confirmations. The separate
flag `all_producer_predicates_independently_recomputed=false` makes this explicit.
Some producer predicates are asserted rather than independently recomputed.
This validator does not turn those assertions into external verification.

## Reviewer procedure

1. Run the dedicated controlled E2E workflow.
2. Keep original report.json/evidence.json, CI event metadata and the exact
   *tested* checkout SHA. On PRs this is ordinarily a synthetic merge SHA, not
   the PR head SHA.
3. From that exact checkout, with artifacts restored, invoke:

    python -m scripts.validation.verify_reviewer_proof_contract_v1 \
      --contract contracts/reviewer-proof-contract-v1.json \
      --report artifacts/real-decision-to-effect-e2e/report.json \
      --evidence artifacts/real-decision-to-effect-e2e/evidence.json \
      --tested-sha "$TESTED_SHA" \
      --source-sha "$SOURCE_SHA" \
      --base-sha "$BASE_SHA" \
      --output reviewer-proof-validation.json

In CI, run mutation tests AFTER the E2E generates controlled test
artifacts (produced by this system; their provenance is not independently
authenticated):

    PYTHONPATH=. pytest tests/validation/test_reviewer_proof_contract_v1.py -q

The mutation-test fixture **fails the test run** with
`REQUIRED_CONTROLLED_E2E_EVIDENCE_MISSING` if either report.json or
evidence.json is absent. It never silently SKIPs required evidence tests.
Therefore the command is intentionally not a stand-alone no-artifact unit test;
run the existing controlled E2E first.

## Explicit nonclaims

This does not prove unauthorized-action refusal, full Bind bypass coverage,
independent administration/custody, real customer or financial effects,
Strict RC1 physical timing/STOP closure, external UTC trust, production
availability or regulatory/third-party certification. Hashes alone cannot
prove origin authenticity if the producer controls every input. No provider
dispatch, credential change or production policy activation is added.
