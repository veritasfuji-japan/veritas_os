# External Bind Integration Path

This is the shortest reviewer path through the current reference integration
assets. It describes boundaries between decision review, payload preparation,
and external execution; it is not a deployment recipe.

## Path at a glance

1. Treat AI or application output as a **Decision Candidate**, not authority to
   act.
2. An integrator may use the [minimal Python SDK](../../../sdk/python/README.md)
   to submit that candidate context to `POST /v1/decide`.
3. Treat the `/v1/decide` response as a governance decision. The endpoint does
   **not** authorize or execute an external side effect.
4. The application may prepare a non-executing bind payload. The import-safe
   [AML/KYC example](../../../sdk/python/examples/aml_kyc_webhook_bind.py)
   demonstrates this separation with synthetic data.
5. Before any real external effect, the proposed action must separately cross
   the **Bind Boundary**, including applicable admissibility, authority, audit,
   and failure controls.
6. [WebhookBindAdapter](webhook-bind-adapter.md) is the reference external bind
   adapter pattern. It uses snapshot, action, and postcondition endpoints; it
   must not be bypassed by sending a prepared payload directly to a target.
7. Verify the postcondition and recorded bind outcome before claiming an action
   **committed**. Claim **rolled back** only when compensation is configured,
   attempted, and explicitly verified; otherwise report the failure without a
   rollback claim.

For a domain-oriented walkthrough, see the
[AML/KYC SDK to Webhook Bind guide](aml-kyc-sdk-webhook-example.md).

## Boundaries and non-claims

These assets are reference integration aids. They do not establish production
certification, a live bank integration, regulatory approval, or a customer
deployment. Integrators remain responsible for deployment-specific security,
human review, data handling, and external-system controls.
