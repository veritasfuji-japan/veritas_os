# Operator Guide: Policy Bundle Promotion (Bind-Boundary Workflow)

This guide describes the operator-facing workflow for:

- `POST /v1/governance/policy-bundles/promote`

It is part of VERITAS OS Decision Governance OS operations and uses the existing
bind-boundary execution path.

VERITAS is not positioned as a generic runtime replacement; this endpoint is an
operator-facing governance control-plane path.

---

## What this endpoint does

`POST /v1/governance/policy-bundles/promote` promotes the active policy bundle
pointer through bind-boundary adjudication and returns bind receipt lineage in
the API response.

The endpoint requires governance write permission.

### Browser/BFF authorization

The browser proxy `/api/veritas/v1/governance/policy-bundles/promote` requires an
authenticated **admin** BFF session, for both bearer-token and session-cookie
authentication. Viewer/operator requests are refused before the proxy calls the
backend. The governance page enables promotion only for an authenticated admin;
selecting an admin UI preview role cannot grant that authority.

Previously the BFF and promotion form also allowed the operator role, despite
the backend requiring `governance_write` (granted only to its admin role).
Because the BFF supplies a shared backend key, the proxy must enforce this
restriction itself: the forwarded `X-Role` does not reduce that key's backend
permissions. Backend governance access, tenant, approval and Bind checks still
apply independently. The prior forwarding mismatch does not prove that those
additional checks could be bypassed or that a real promotion occurred.

The regression uses the actual BFF route handlers with mocked upstream fetch
and tests viewer/operator refusal, admin forwarding, forged role/key headers,
and both credential modes. UI tests cover the authenticated role versus the
preview selector. This does not establish per-user backend identities, tenant
isolation, or production deployment safety.

---

## When to use it

Use this endpoint when an approved governance decision needs to move runtime to
another already-present policy bundle directory (for example, from `bundle-v1`
to `bundle-v2`) while preserving bind execution lineage.

## Current bind policy surface (operator fact)

Current implemented operator-governed bind paths include:

1. `POST /v1/governance/policy-bundles/promote` (this guide)
2. `PUT /v1/governance/policy` (governance policy update path)
3. `PUT /v1/compliance/config` (runtime compliance config mutation path)

Do not claim that all effect paths are bind-governed yet.

---

## Request fields and meaning

Required fields:

- `decision_id`: decision artifact identifier tied to this promotion intent.
- `request_id`: request lineage identifier.
- `policy_snapshot_id`: policy snapshot identifier used for bind lineage.
- `decision_hash`: decision hash used by bind execution intent.

Bundle selector (exactly one is required):

- `bundle_id`
- `bundle_dir_name`

Optional:

- `approval_context`: additional operator approval metadata.

### Why arbitrary filesystem paths are not accepted

Promotion accepts only a bundle selector name (not an arbitrary path). The API
rejects traversal patterns in selectors, and bundle resolution is constrained to
the configured policy bundles root before bind execution proceeds.

---

## Minimal request example

```bash
curl -X POST "http://127.0.0.1:8000/v1/governance/policy-bundles/promote" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "X-Role: admin" \
  -H "Content-Type: application/json" \
  -d '{
    "bundle_id": "bundle-v2",
    "decision_id": "dec-promote-1",
    "request_id": "req-promote-1",
    "policy_snapshot_id": "snap-promote-1",
    "decision_hash": "hash-promote-1",
    "approval_context": {"policy_bundle_promotion_approved": true}
  }'
```

---

## Response fields: how to read result

- `bind_outcome`: terminal bind outcome classification.
- `bind_failure_reason`: compact operator-facing reason when not clean commit.
- `bind_reason_code`: stable reason code if provided by bind checks.
- `bind_receipt_id`: bind receipt lineage identifier.
- `execution_intent_id`: bind execution intent lineage identifier.
- `bind_summary`: compact shared bind vocabulary reused across bind-governed mutation/export responses.
- `bind_receipt`: full receipt payload with check results and canonical target metadata.

This is the public bind outcome contract for governance-facing operator flow.

### Representative `bind_outcome` values

- `COMMITTED`
- `BLOCKED`
- `ROLLED_BACK`
- `ESCALATED`
- `APPLY_FAILED`
- `SNAPSHOT_FAILED`
- `PRECONDITION_FAILED`

---

## Failure triage checklist

When promotion does not cleanly commit:

1. Check `bind_reason_code` first for machine-stable cause category.
2. Check `bind_failure_reason` for compact operator summary.
3. Inspect `bind_receipt` for authority / constraint / drift / risk check details.
4. Retrieve persisted receipt lineage through list/export/detail surfaces:
   - `GET /v1/governance/bind-receipts`
   - `GET /v1/governance/bind-receipts/export`
   - `GET /v1/governance/bind-receipts/{bind_receipt_id}`
5. Correlate with decision exports if needed:
   - `GET /v1/governance/decisions/export`

## Receipt replayability note

Bind receipts can be treated as replay/revalidation-oriented governance artifacts.
Use this wording as current direction and avoid claiming complete cross-path
standardization in this release.

---

## Related endpoints

- `GET /v1/governance/bind-receipts`
- `GET /v1/governance/bind-receipts/export`
- `GET /v1/governance/bind-receipts/{bind_receipt_id}`
- `GET /v1/governance/decisions/export`
