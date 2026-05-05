# Recent Hardening Notes

This note summarizes recent engineering hardening work across auditability, observability, CI quality gates, API compatibility, and dependency-risk visibility.

## Scope

These changes improve operational confidence around VERITAS OS without changing the core governance contract.

## Hardening summary

### Auditability
- RBAC denial events are now recorded as privacy-safe signed audit events in TrustLog.
- RBAC denial fields are preserved even after compact signed TrustLog summaries are generated.

### Observability
- Structured JSON logging can be enabled for operational telemetry with trace correlation.
- Request trace IDs are propagated through API middleware and logs to support cross-component tracing.

### Quality gates
- Replay report checks support strict mode and `--require-reports` to fail closed when required report evidence is missing.
- Pytest discovery roots are explicit for both `veritas_os/tests` and top-level `tests`.

### API reliability
- `/v1/decide` response coercion preserves bind compatibility fields sourced from nested bind data.
- OpenAPI generation includes a guard against a known third-party Pydantic deprecation warning.

### Dependency-risk visibility
- CI includes a non-blocking lane for future FastAPI/Pydantic compatibility dry runs.
- That lane publishes resolved versions, targeted tests, pytest result, and exit code in GitHub Actions summaries.

## What this does not claim

- This note does not claim full future compatibility with every FastAPI/Pydantic release.
- This note does not make the future dependency lane a blocking gate.
- This note does not change production dependency pins.
- This note does not replace external security or compliance review.

## Reviewer checklist

When reviewing future changes, check:
- Are audit events privacy-safe?
- Do quality gates fail closed when required evidence is missing?
- Are CI lanes clear about blocking vs non-blocking status?
- Are dependency-risk signals visible without changing production pins?
