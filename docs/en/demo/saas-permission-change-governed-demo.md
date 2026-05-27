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
