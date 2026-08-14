# External Bind Boundary PoC Evidence

Run this repository-local, synthetic demonstration from the repository root:

```bash
python scripts/demo/run_external_bind_poc.py
```

The command needs no internet access or credentials. It starts a loopback-only
HTTP fixture, executes three scenarios, shuts the fixture down, prints a short
PASS summary, and writes canonical JSON to `artifacts/external-bind-poc/`.

## Reviewer scenarios

- **COMMITTED:** valid authority and state fingerprint cause exactly one action
  POST; its postcondition is verified before the receipt commits.
- **BLOCKED:** missing authority stops execution at the Bind Boundary, so the
  receiver observes zero action POSTs and evidence includes the refusal reason.
- **ROLLED_BACK:** the action succeeds, the postcondition deliberately fails,
  compensation runs, restored state is snapshotted, and rollback is reported
  only after verification.

Each scenario artifact includes stable decision and intent IDs, final outcome,
idempotency and rollback status, sanitized target description, external POST
counts, receipt hash, and verification details. `manifest.json` indexes them.

## Security boundary

`WebhookBindAdapter` continues to reject private and loopback targets. The PoC
uses its injectable transport and resolver: the adapter validates a synthetic
public HTTPS host, while the **test-only** transport maps approved requests to
the loopback fixture. This preserves the adapter request flow without weakening
production SSRF protections. Do not reuse the fixture transport in production.

## Decision-stage limitation

This PoC **does not call the VERITAS `/v1/decide` runtime**. It starts with a
deterministic synthetic Decision Candidate, recorded in every artifact as
`"decision_stage":"synthetic_fixture"`. Running the real decision pipeline
locally requires provider, TrustLog, and runtime configuration; replacing those
dependencies with a hard-coded pipeline response would not prove that runtime.

The real VERITAS runtime exercised here begins at `execute_bind_adjudication`
and includes authority, constraint, drift, and risk adjudication, the real
`WebhookBindAdapter` request flow, postcondition verification, compensation,
rollback verification, and receipt construction. The external receiver and its
transport mapping remain synthetic test fixtures.

This PoC demonstrates the behavior of the reference bind path in a controlled local test environment. It is not evidence of a production deployment, regulatory certification, or integration with a live financial institution.

It also does not prove production readiness, customer deployment, live bank
connectivity, availability, or deployment-specific security controls. All data
is synthetic and generated evidence contains no HMAC secret or API key.
