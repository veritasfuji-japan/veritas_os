# Evaluation Receipt v1

## 1. Purpose

Evaluation Receipt v1 records how a specific admissibility evaluation was
performed at bind/evaluation time. The receipt makes the evaluation function
visible, replayable, attributable, and auditable by recording the governed state
that participated in one evaluation instance.

The v1 receipt does not enforce behavior. It is a schema-only foundation for
reviewers and future tooling to inspect what the evaluator claimed to use and
what admissibility outcome it produced.

## 2. Relationship to Evaluation Function Manifest

The Evaluation Function Manifest defines the governed evaluation mechanism. It
names the evaluator, evaluator version, policy identity, rule-set version,
authorized determiners, admissibility inputs, qualifier sources, refusal
boundaries, escalation resolver, and root authority manifest reference.

The Evaluation Receipt records a specific use of that mechanism. It points back
to the Evaluation Function Manifest and records the evaluation-time state that
was actually used, including hashes that support later replay, comparison, and
drift analysis.

In short:

- **Evaluation Function Manifest** defines what the governed evaluator is allowed
  to be.
- **Evaluation Receipt** records what one evaluation instance did with that
  governed evaluator.

## 3. What the receipt captures

An Evaluation Receipt captures:

- evaluator identity and version
- policy identity and rule-set version
- Evaluation Function Manifest reference and hash
- Root Authority Manifest reference
- authority evidence references
- qualifier state, source references, freshness state, and qualifier hashes
- authorized determiners used and whether each determiner influenced the outcome
- admissibility inputs, input references, required flags, and input hashes
- consequence class and classifier metadata
- material context reference, freshness state, stale-context allowance, and hash
- admissibility outcome
- rationale codes explaining the outcome
- input-state, evaluation-state, and receipt hashes for later comparison

These fields are intended to make the evaluation attributable without declaring
that the evaluation was automatically legitimate.

## 4. Evaluation consistency

Future Evaluation Drift Detection can compare Evaluation Receipts to determine
whether outcome changes are attributable to explicit governed causes, including:

- governed state change
- policy identity change
- rule version change
- authority state change
- qualifier freshness change
- evaluator version change
- unauthorized determiner influence
- unexplained evaluation drift

Evaluation Receipt v1 does not perform this attribution at runtime. It only
provides the schema foundation needed for later comparison and review.

## 5. v1 scope

Evaluation Receipt v1 is intentionally limited:

- schema-only
- no runtime enforcement
- no automatic legitimacy judgment
- no `/v1/decide` behavior change
- no production governance mutation
- no fail-closed integration yet

This PR does not modify bind/admissibility logic, production governance
configuration, policy loading, TrustLog persistence, or FUJI Gate behavior.

## 6. Future work

Future work can build on Evaluation Receipt v1 with:

- Outcome Delta Attribution
- Evaluation Drift Detection
- Trajectory-Level Admissibility Monitor
- Legitimacy Impact Review
- Runtime fail-closed integration
- Receipt generation from live bind/admissibility paths
