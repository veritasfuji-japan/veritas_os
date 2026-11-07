# Reviewer Proof Contract v1: Controlled Decision-to-Effect

This is an offline, fail-closed consistency and checkout-provenance gate for
the existing controlled Decision-to-Effect E2E. It is NOT an independently
executed test, real customer effect, certification or deployment assurance.

## Files

- Contract: contracts/reviewer-proof-contract-v1.json
- Validator: scripts/validation/verify_reviewer_proof_contract_v1.py
- Negative tests: tests/validation/test_reviewer_proof_contract_v1.py
- Existing producer: .github/workflows/reproducible-decision-to-effect-e2e.yml
- Generated evidence: artifacts/real-decision-to-effect-e2e/report.json and evidence.json

The existing E2E uses real TLS and PostgreSQL but synthetic controlled
business effects and credentials. The new gate validates full frozen
predicate coverage (18 keys), two specific normal and lost-response cases,
the exact negative production claims, report/evidence case identities,
canonical SHA-256 digests and actual checked-out commit provenance.

A SHA-256 value establishes consistency of files, not independent authorship
or authenticity. The report's own PASS booleans are self-produced: this gate
does not independently reconstruct execution events. An independent reviewer
should retain the exact Git checkout, workflow run, original artifacts, and
operational evidence before accepting any stronger claim.

## Scope

Normal: HTTP 201 matching ACK, confirmed synthetic effect and at least three
governance rechecks.

Fault: lost response, lookup outage remains EFFECT_UNKNOWN, retry prohibited,
exactly one transport call, eventual confirmed synthetic effect and at least
three governance rechecks.

NOT covered by this contract: missing approval, attacker target mutation,
32-way concurrency, universal bypass resistance, independent custody, real
customer effect, physical time/STOP/Strict RC1 closure, real external UTC
trust, production SLA, independent security audit, regulatory certification.

For other scenarios consult their separate proof/test contracts. Never
describe the combined evidence as one universal security guarantee.

## Run

1. Run the existing dedicated controlled Decision-to-Effect E2E workflow.
2. Obtain the original run artifacts and event metadata, including tested SHA,
   source/head SHA and base SHA. On pull requests the tested SHA is normally a
   synthetic merge commit; do not replace it with the PR head SHA.
3. Check out the exact tested commit and restore report.json and evidence.json.
4. Invoke the verifier from repository root:

    python scripts/validation/verify_reviewer_proof_contract_v1.py \
      --contract contracts/reviewer-proof-contract-v1.json \
      --report artifacts/real-decision-to-effect-e2e/report.json \
      --evidence artifacts/real-decision-to-effect-e2e/evidence.json \
      --tested-sha "$TESTED_SHA" \
      --source-sha "$SOURCE_SHA" \
      --base-sha "$BASE_SHA" \
      --output reviewer-proof-validation.json

5. A PASS_BOUNDED_CONSISTENCY_ONLY result does not imply independent effects,
   production readiness or third-party certification.

Unit regression tests (no database/network):

    PYTHONPATH=. pytest -q tests/validation/test_reviewer_proof_contract_v1.py

No paid provider calls, real external mutations, changes to authorization
semantics or live policy activation are performed by this contract.
