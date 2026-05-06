# Governance Trace Span Chain

## Purpose

This document defines what VERITAS OS currently traces for the governance policy update path, what attributes are privacy-safe, and what remains out of scope. It is intended for external reviewers, HPAN reviewers, and enterprise audit teams validating observability boundaries.

## What is implemented

VERITAS OS currently implements:

- OpenTelemetry-compatible tracing helpers with fail-safe no-op fallback.
- Root request span in API middleware.
- Governance policy update span chain.
- RBAC denial span event emission.
- Span attribute attachment after span activation.

## Expected span chain for governance policy update

For `PUT /v1/governance/policy`, the expected span chain is:

1. `http.request` (middleware root span)
2. `governance.policy_update.request`
3. `governance.approval.validate`
4. `governance.bind_boundary.evaluate`
5. `bind.boundary.evaluate.start` (event)
6. `bind.boundary.evaluate.end` (event)
7. `governance.policy.persist`
8. `governance.policy_update.response`

Notes:

- `bind.boundary.evaluate.start` and `bind.boundary.evaluate.end` are emitted as trace events in the bind evaluator path; they are listed here because reviewers expect to validate the full chain, including boundary evaluation lifecycle markers.
- `governance.approval.validate` is a validation step span executed before bind boundary evaluation.

## Expected event for RBAC denial

When RBAC rejects a permission check, the active span receives the event:

- `rbac.denied`
- `rbac.denial.audit_append`

This event records denial metadata only (for example, role, permission, endpoint, method, reason code, trace id) and must not include secrets.
For `rbac.denial.audit_append`, `audit_append_status = success | failed | deduped` tracks best-effort TrustLog append outcomes without changing RBAC deny semantics or API responses.

## Privacy-safe attribute policy

Trace attributes and events must remain operationally useful while avoiding secret and personal data leakage.

## Attributes currently expected

Current implementation and tests rely on the following attribute keys:

- `trace_id`
- `http.method`
- `http.route`
- `veritas.component`
- `status_code`
- `decision_id`
- `request_id`
- `actor_identity`
- `policy_snapshot_id`
- `approval_count`
- `bind_receipt_id`
- `final_outcome`
- `bind_reason_code`
- `target_path`
- `target_type`
- `event_type`
- `reason_code`
- `actor_role`
- `requested_permission`
- `endpoint`
- `method`
- `audit_append_status`
- `error_type`

## Attributes explicitly forbidden

The following must never be written into span attributes or events:

- `Authorization`
- `X-API-Key`
- `Cookie`
- `token`
- `secret`
- `password`
- raw request body
- `query_string`
- personally identifying free-text payloads
- approval signature raw secret beyond existing v1 token string semantics
- medical/financial record contents

## No-op fallback behavior

Tracing helpers are fail-safe by design:

- If OpenTelemetry is unavailable, span helpers degrade to no-op behavior.
- If tracing APIs fail at runtime, business logic continues without breaking request flow.
- Therefore, missing OpenTelemetry dependencies or runtime tracer backend does not change governance, bind, or RBAC semantics.

## Current non-goals / not implemented

The following are explicitly out of scope for the current implementation:

- Jaeger deployment
- Grafana/Tempo dashboard
- OTLP exporter configuration
- production collector
- cryptographic human approval signature
- backend TrustLog append guarantee changes
- full distributed tracing across external services
- frontend visual trace viewer

## How to verify locally

Important:

- In environments without an OpenTelemetry exporter, spans may be no-op or may not appear in external trace UIs.
- Current verification primarily uses unit tests, fake tracer tests, and monkeypatch-based tracing tests.

Run:

- `pytest -q veritas_os/tests/test_trace_span_chain.py`
- `pytest -q veritas_os/tests/unit/test_auth_rbac_audit.py`
- `pytest -q veritas_os/tests/test_middleware_core.py`

## External reviewer checklist

Use this checklist during review:

1. Confirm governance update path emits expected span names and boundary events.
2. Confirm RBAC denial emits `rbac.denied` event with safe metadata.
3. Confirm privacy-safe attributes are present and useful for auditing.
4. Confirm forbidden attributes are absent from span attributes/events.
5. Confirm no-op fallback behavior is documented and tested.
6. Confirm this scope does not include Jaeger/Grafana/OTLP deployment work.
