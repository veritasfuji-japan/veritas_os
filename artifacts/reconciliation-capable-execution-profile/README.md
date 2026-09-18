# Reconciliation-Capable Execution Profile Proof Artifacts

This directory is the runtime artifact destination for the dedicated controlled
proof of the policy-gated reconciliation-capable execution profile.

The committed repository does not treat generated `report.json` or
`evidence.json` as static truth. The GitHub Actions workflow regenerates them
for the exact source SHA under test.

## Workflow

`.github/workflows/reproducible-reconciliation-capable-execution-profile.yml`

Job:

`reproducible-reconciliation-capable-execution-profile`

## Runtime outputs

The workflow generates and uploads:

- `report.json` — machine-readable proof conjunction and non-claims;
- `evidence.json` — source-SHA-bound decision, authorization, capability,
  consumption, reconciliation and receipt evidence; and
- the controlled sandbox service log.

## Proven controlled path

The positive path requires authoritative reconciliation capability before
authorization consumption and then exercises:

```text
/v1/decide
-> CanonicalDecisionArtifact verification
-> deterministic promotion / ExecutionIntent
-> native v2 authorization
-> policy-required AUTHORITATIVE_QUERY capability
-> current target / verifier / evidence-digest recheck
-> PostgreSQL single-use authorization consumption
-> controlled pre-effect checks
-> certificate-validated TLS POST
-> EFFECT_UNKNOWN
-> independent read-only reconciliation
-> CONFIRMED_EFFECT
-> BindReceipt / Outcome
```

The fault path loses the observed response after the sandbox event persists,
preserves `EFFECT_UNKNOWN` through a controlled lookup outage, prohibits blind
redispatch, and confirms the exact persisted operation after lookup recovery.

## Fail-closed cases

The dedicated proof also demonstrates with real PostgreSQL that:

- required capability missing -> authorization remains unconsumed;
- `HEURISTIC_ONLY` capability -> authorization remains unconsumed; and
- neither blocked path creates a sandbox event.

The broader focused gate matrix is run in the same workflow and covers expiry,
endpoint/configuration drift, verifier mismatch, digest mismatch, incomplete
policy, and request-like policy downgrade attempts.

## Claim boundary

A passing workflow proves a **controlled policy-gated execution profile** with
synthetic decisions, credentials, keys and business effects.

It does not prove:

- production readiness;
- a real customer endpoint;
- universal downstream reconcilability;
- exactly-once external delivery;
- external UTC production trust;
- regulatory approval or certification.

The frozen Controlled Execution Proof v1 remains a separate claim and is not
rewritten by this profile proof.
