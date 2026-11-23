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
