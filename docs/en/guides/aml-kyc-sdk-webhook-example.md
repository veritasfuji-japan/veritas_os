# AML/KYC Decision Candidate: Python SDK to Webhook Bind

This reference integration example shows how an application can ask VERITAS
OS to review a placeholder AML/KYC case, then prepare data for a separately
governed external bind. It does not use customer data, contact a bank, or
perform an external action. It is not a production integration, certification,
regulatory approval, or compliance determination.

## Boundary at a glance

1. The application prepares a placeholder review request.
2. The [minimal Python SDK](../../../sdk/python/README.md) calls
   `POST /v1/decide`.
3. The response is retained as a **Decision Candidate / governance decision**,
   not permission to execute.
4. The application may prepare a non-executing bind payload for review.
5. Any actual external action must separately cross the **Bind Boundary**. The
   [WebhookBindAdapter](webhook-bind-adapter.md) is the reference external bind
   adapter pattern; it applies bind adjudication and its documented external
   execution controls rather than treating the SDK response as authorization.

`/v1/decide` evaluates a request and returns a decision response. It does not
execute an external action. The SDK only helps an application call VERITAS; it
does not replace bind admissibility, authority, audit, or failure controls.

## Import-safe, non-executing example

The import-safe
[`aml_kyc_webhook_bind.py`](../../../sdk/python/examples/aml_kyc_webhook_bind.py)
example defines the integration steps but does not call the API or an external
system when imported or run. An application must explicitly call
`request_review()` to contact its configured VERITAS deployment. The
`prepare_bind_payload()` function only constructs application data for a later
reviewed bind flow.

```python
from typing import Any

from veritas_client import VeritasClient


def build_review_payload() -> dict[str, Any]:
    """Build a fictional AML/KYC review request with no customer data."""
    return {
        "query": (
            "Which review disposition should an analyst consider for the "
            "placeholder case?"
        ),
        "options": [
            "request_additional_documentation",
            "escalate_for_human_review",
            "record_no_further_action_candidate",
        ],
        "context": {
            "case_id": "placeholder-case-001",
            "risk_signals": [
                "placeholder_identity_mismatch",
                "placeholder_source_of_funds_review",
            ],
            "data_classification": "synthetic_example_only",
        },
    }


def request_review(client: VeritasClient) -> dict[str, Any]:
    """Request a governance decision that remains a Decision Candidate."""
    return client.decide(build_review_payload())


def prepare_bind_payload(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Prepare, but do not execute, data for a reviewed bind workflow."""
    return {
        "decision_id": decision.get("decision_id"),
        "adapter_pattern": "WebhookBindAdapter",
        "target": "https://example.invalid/aml-kyc-review",
        "action_payload": {
            "case_id": "placeholder-case-001",
            "requested_operation": "create_human_review_task",
        },
        "execution_status": "not_executed",
        "requires_bind_adjudication": True,
    }
```

For example, an application can construct a client with locally supplied
configuration and explicitly request the review:

```python
client = VeritasClient(
    base_url="http://localhost:8000",
    api_key="your-local-api-key",
)
candidate = request_review(client)
bind_payload = prepare_bind_payload(candidate)
```

At this point, `bind_payload` is still only application data. Do not send it
directly to the placeholder target. A reviewed integration must map it to the
existing bind contract and cross the Bind Boundary through the
`WebhookBindAdapter` pattern (or another approved adapter) before any side
effect can occur.

## Integration and security notes

- Use synthetic data while evaluating this example; do not copy real identity,
  account, sanctions-screening, or customer records into source code or logs.
- Keep API keys and webhook signing secrets outside code, use least-privilege
  access, and use verified HTTPS for non-local deployments.
- Validate the deployed `/v1/decide` request and response contract. Treat both
  decision and error payloads as potentially sensitive.
- Do not infer approval from an HTTP success response or a favorable Decision
  Candidate. Human review and deployment-specific AML/KYC controls remain the
  integrator's responsibility.
- Follow the `WebhookBindAdapter` guidance for target allowlisting, signing,
  idempotency, postcondition verification, and fail-closed handling.
