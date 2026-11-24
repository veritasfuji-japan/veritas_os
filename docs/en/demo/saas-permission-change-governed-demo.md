# SaaS Permission-Change Governed Execution Demo (Local/Offline Fixture)

This demo is a **local/offline fixture** showing how VERITAS governs an AI agent attempt to change SaaS permissions before execution.

Scenario: an AI agent attempts to grant `admin` access (`saas:grant_admin`) to an external contractor account.

- Script: `scripts/demo/saas_permission_change_governed_demo.py`
- Tests: `tests/demo/test_saas_permission_change_governed_demo.py`

## What it demonstrates

VERITAS checks the following before commit-boundary execution:

1. Authority evidence (Authority Evidence Ingestion v1 output)
2. Human approval receipt (Human Approval Receipt v1 output)
3. Runtime authority validation and bind-time commit-boundary evaluation

Fail-closed behavior is demonstrated for:

- missing authority evidence
- missing human approval
- expired human approval
- scope mismatch between requested scope and granted/approved scope

When both authority evidence and human approval are valid for `saas:grant_admin`, the action becomes commit-eligible (`commit` in the current evaluator vocabulary).

## Deterministic fixture cases

The demo runs deterministic cases with fixed timestamps and fixture IDs:

- `missing_authority` → block
- `missing_human_approval` → block
- `expired_human_approval` → block
- `scope_mismatch` → block
- `valid_authority_and_approval` → commit

## Local boundary / non-goals

This fixture is local/offline only.

It does **not** connect to live:

- SaaS providers
- IdP / IAM / SSO
- customer directories
- email systems
- production approval workflows

This is **not** legal advice, regulatory approval, third-party certification, or production access-control validation.

## Test-tenant role grant rehearsal

A separate integration test uses the real Sandbox Bind execution and
reconciliation paths with a synthetic directory. The native authorization binds
the exact fixture tenant, user, and limited `report-viewer` role encoded in the
Sandbox event before issuance. The directory updates its in-process state only
when it receives a POST through the real transport code. The test replaces the
network connection with an in-process stream.

| Case | Expected observation |
| --- | --- |
| Exact grant | One POST changes one membership. A matching acknowledgement leaves the attempt in `EFFECT_UNKNOWN` until reconciliation. |
| Changed tenant, user, or role | Zero connections and zero membership changes. |
| Authority revoked when rechecked | Zero connections and zero membership changes. |
| Replay of the same authorization | Zero additional POSTs or membership changes. |
| Write succeeds and its response is lost | The attempt stays in `EFFECT_UNKNOWN`. A read-only GET by the original key confirms the recorded effect without another write. |

```sh
python -m pytest -q veritas_os/tests/test_saas_role_grant_bind_rehearsal.py
```

The rehearsal uses in-memory Bind stores, a fixture clock, and synthetic writer
and reader identities. It exercises the existing Sandbox action class. A real
SaaS/IdP integration and provider-side role enforcement require separate
validation in the selected test tenant.

## Self-hosted Keycloak role-grant rehearsal

The opt-in Keycloak integration test starts with a fresh realm in a disposable,
loopback-only Keycloak server. It binds the realm, user UUID, client UUID, and
role UUID to the existing Sandbox authorization. A test-only bridge checks the
bound command and maps it to the Keycloak Admin REST role-mapping API. The
bridge uses separate Keycloak service accounts for writing and reading. The
test verifies that Keycloak returns HTTP 403 when the read-only account attempts
the write operation.

The rehearsal checks that substituted identifiers and a revoked authority cause
zero writes. It then observes one successful Keycloak POST, drops the response
at the Sandbox boundary, and checks that the same authorization cannot send
again. A simulated lookup outage keeps the outcome unknown. A subsequent GET of
the actual role mapping in Keycloak supplies the observation used to reconcile
the outcome.

The rehearsal also injects a timeout at the bridge's Keycloak HTTP client.
One case drops the request before forwarding. The other forwards it to the
real Keycloak server and withholds the successful response from the bridge.
The read-only lookup sees no role in the first case and sees the new role in
the second. In both cases the observation lacks evidence tying it to the
original request, so the attempt stays in `EFFECT_UNKNOWN` and rejects replay.

The workflow `Keycloak Bind Role Rehearsal` provisions the disposable server
and runs this test. To reproduce locally with Docker, run these commands from
the checkout after installing the repository's Python test dependencies.

```sh
export KC_BOOTSTRAP_ADMIN_USERNAME=fixture-admin
export KC_BOOTSTRAP_ADMIN_PASSWORD="$(openssl rand -hex 32)"
docker run --rm -d --name keycloak-bind-proof -p 127.0.0.1:18080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME -e KC_BOOTSTRAP_ADMIN_PASSWORD \
  quay.io/keycloak/keycloak:26.8.2 start-dev
```

After the server is ready, run the test and remove the container.

```sh
VERITAS_KEYCLOAK_REHEARSAL=1 python -m pytest -q \
  veritas_os/tests/test_keycloak_bind_role_rehearsal.py
docker stop keycloak-bind-proof
unset KC_BOOTSTRAP_ADMIN_USERNAME KC_BOOTSTRAP_ADMIN_PASSWORD
```

The bridge supplies the Sandbox operation envelope from the observed role
mapping and the test's known write association. Keycloak provides the role
mapping, while the correlation is scoped to the isolated run. The rehearsal
uses in-memory Bind stores, an in-process Sandbox transport connection, and
loopback HTTP to Keycloak. Live TLS, durable recovery, and a deployed Keycloak
adapter require separate validation.
