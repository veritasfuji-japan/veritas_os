# External Bind Integration Milestone

This milestone brings the recently merged external bind reference assets into
one reviewer-traceable path:

- `WebhookBindAdapter` is now the reference external bind adapter pattern.
- A minimal Python SDK is available under [`sdk/python/`](../../../sdk/python/README.md).
- An import-safe, synthetic [AML/KYC reference example](../../../sdk/python/examples/aml_kyc_webhook_bind.py)
  demonstrates SDK use and non-executing bind-payload preparation.
- The [External Bind Integration Path](../guides/external-bind-integration-path.md)
  connects these assets, with supporting guides for the
  [WebhookBindAdapter](../guides/webhook-bind-adapter.md) and the
  [AML/KYC SDK-to-webhook flow](../guides/aml-kyc-sdk-webhook-example.md).

## What reviewers can trace

Reviewers can follow a Decision Candidate through the SDK call, preparation of
a non-executing bind payload, separate Bind Boundary adjudication, and outcome
verification. The SDK response and prepared payload do not authorize or
perform an external action.

## Boundaries and non-claims

These reference assets do **not** claim production certification, a live bank
integration, regulatory approval, or a customer deployment.
