# Webhook Bind Adapter

`WebhookBindAdapter` is a reference external bind adapter for evaluating VERITAS OS bind execution against an HTTPS webhook target. It connects an existing `ExecutionIntent` to the existing bind adjudication flow and does not create a new bind engine, API route, UI, SDK, or decorator.

## Status and purpose

This adapter is currently a prototype/evaluation reference for external bind integration. It is not certification, not regulatory approval, and not evidence of production customer deployment. Deployment-specific authentication, network policy, secret management, and mTLS remain integrator responsibilities.

## Required three-endpoint flow

The adapter uses three HTTPS endpoints:

1. **Snapshot**: `GET snapshot_url` returns the current external state as a JSON object.
2. **Action**: `POST action_url` applies the governed action payload.
3. **Postcondition**: `GET postcondition_url` returns a JSON object that must recursively contain the configured expected postcondition.

An optional compensation endpoint can be configured. Generic external effects may be irreversible. When compensation is absent, fails, or cannot be verified, rollback is not claimed.

Drift-sensitive execution requires the `ExecutionIntent` to carry the
decision-time `expected_state_fingerprint`. The adapter fingerprints the live
snapshot with canonical JSON and SHA-256; a missing or mismatched expected
fingerprint fails closed before the action endpoint is called.

## HMAC request format

Action and compensation requests are JSON `POST` requests with redirects disabled and a bounded timeout. Receivers should expect:

```text
Content-Type: application/json
X-Veritas-Decision-Id: <decision id>
X-Veritas-Execution-Intent-Id: <execution intent id>
X-Veritas-Idempotency-Key: <deterministic adapter key>
X-Veritas-Timestamp: <UTC timestamp>
X-Veritas-Signature: sha256=<lowercase hex hmac-sha256>
```

The signature input is:

```text
X-Veritas-Timestamp + "." + canonical_json_body
```

The HMAC secret is never included in the idempotency key, target description, bind receipt, or response evidence.

## Idempotency

The adapter idempotency key is deterministic over the execution intent id, decision id, normalized action URL, and canonical action payload. It does not use Python `hash()`, current time, or the HMAC secret.

## Sample receiver responses

Snapshot response:

```json
{"account": {"status": "active", "limit": 100}}
```

Action response:

```json
{"accepted": true, "operation_id": "op-123"}
```

Postcondition response:

```json
{"account": {"status": "active", "limit": 120}}
```

With `expected_postcondition={"account": {"limit": 120}}`, the postcondition passes because the expected object is a recursive subset of the returned object.

## Fail-closed behavior

The adapter fails closed on timeout, connection failure, malformed JSON, non-object JSON, non-2xx responses, unverifiable postconditions, unsafe URLs, missing approval, constraint failure, or runtime-risk failure. BLOCKED and ESCALATED decisions do not execute the action webhook.

Rollback is claimed only after a successful compensation response is followed
by a fresh snapshot whose canonical fingerprint exactly matches the original
pre-bind snapshot. A successful compensation HTTP response alone is not proof
that an external effect was restored.

Outbound URL validation is intentionally restrictive by default:

- HTTPS only
- explicit host allowlist required
- no URL userinfo
- no fragments
- malformed ports rejected
- redirects disabled
- localhost, loopback, link-local, multicast, unspecified, private, and reserved addresses rejected

These controls reduce common outbound request and SSRF risks, but they are not
a claim of complete SSRF resistance. Integrators must also enforce
deployment-specific egress and DNS policy.

## What is not yet provided

This PR does not provide a separate SDK package, `@veritas.govern` decorator, public API route, UI, customer demo, production-readiness claim, certification claim, or regulatory approval claim.

## Planned SDK layer

A later SDK layer can wrap receiver scaffolding, secret management guidance, mTLS integration patterns, and developer ergonomics around this reference adapter without changing the bind core semantics.
