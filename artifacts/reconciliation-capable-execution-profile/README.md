# Reconciliation-Capable Execution Profile Proof Artifacts

This directory is the runtime artifact destination for the dedicated controlled
proof of the policy-gated reconciliation-capable execution profile.

The committed repository does not treat generated `report.json` or
`evidence.json` as static truth. The GitHub Actions workflow regenerates them
for the exact checkout SHA under test.

## Workflow

`.github/workflows/reproducible-reconciliation-capable-execution-profile.yml`

Job:

`reproducible-reconciliation-capable-execution-profile`

## Commit identity and execution conditions

Both dedicated proof workflows run on every pull request, every push to
`main`, and manual dispatch. There are no path filters: API, policy, storage,
migration and dependency changes can affect the proof indirectly.

Both `report.json` and `evidence.json` record:

- `tested_sha`: actual `git rev-parse HEAD`, required to equal the workflow's
  `github.sha`;
- `source_sha`: PR head SHA (retained for compatibility); and
- `base_sha`: PR base SHA.

On a PR, `tested_sha` normally identifies GitHub's synthetic merge commit and
can differ from both metadata SHAs. On a main push or manual dispatch, all three
identify the event's commit. Missing, malformed or mismatched identities fail
the proof; the final artifact check independently verifies both files against
the checkout and event metadata, even if the files agree with each other.

A passing PR run is evidence for its tested merge candidate. Evidence for a
merged main commit requires a successful main run with that exact `tested_sha`.
Failed-run artifacts may still be uploaded for diagnosis and are not PASS
evidence. These fields are CI provenance, not signed attestations or additional
execution authority.

## Runtime outputs

The workflow generates and uploads:

- `report.json` — machine-readable proof conjunction and non-claims;
- `evidence.json` — checkout-SHA-bound decision, authorization, capability,
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
-> deployment-controlled capability verifier
-> runtime-sealed verified capability proof
-> current target / verifier trust-policy / evidence-digest recheck
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

## Verified proof boundary

Raw `ReconciliationCapabilityEvidence` is not treated as self-authenticating.
The controlled profile first sends it through a deployment-controlled verifier
and independently configured verifier trust policy.

The resulting `VerifiedReconciliationCapabilityEvidence` carries the raw
evidence digest, verifier binding, trust-policy binding, verification material
digest, verified timestamp and runtime seal hash.

The runtime seal is process-local. Serializing and reconstructing the same fields
does not create another trusted proof.

## Fail-closed cases

The dedicated proof also demonstrates with real PostgreSQL that:

- required verified capability proof missing -> authorization remains unconsumed;
- raw capability evidence alone -> authorization remains unconsumed;
- verifier-sealed `HEURISTIC_ONLY` capability -> authorization remains unconsumed; and
- neither blocked path creates a sandbox event.

The verifier trust-boundary tests and broader focused gate matrix are run in the
same workflow. They cover caller-constructed proof lookalikes, trust-policy
mismatch, expiry, endpoint/configuration drift, verifier mismatch, digest
mismatch, incomplete policy, and request-like policy downgrade attempts.

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
