# Minimal Python SDK reference

This directory provides a small, synchronous reference client for starting a
VERITAS OS integration. It uses only the Python standard library and calls the
existing `POST /v1/decide` endpoint. Copy `veritas_client.py` into an
application or place this directory on `PYTHONPATH`; this reference is not a
packaged distribution.

## Scope and claims

- This is a minimal reference SDK, **not** a full production SDK.
- It does not claim certification, regulatory compliance, or a live customer
  integration.
- AI output remains a **Decision Candidate**, not authorization to act.
- External execution must separately cross the **Bind Boundary**, including
  the applicable admissibility, authority, audit, and failure controls.
- The bind example only prepares application data. It does not invoke,
  reproduce, or bypass `WebhookBindAdapter` or bind adjudication.

## Requirements

- Python 3.11 or newer
- A running VERITAS OS API and an API key authorized for `/v1/decide`
- No third-party Python dependencies

## Decision example

Run from this directory:

```bash
export VERITAS_BASE_URL="http://localhost:8000"
export VERITAS_API_KEY="your-local-api-key"
PYTHONPATH=. python examples/decide.py
```

Or use the client directly:

```python
from veritas_client import VeritasClient

client = VeritasClient(
    base_url="http://localhost:8000",
    api_key="your-local-api-key",
    timeout=30.0,
)
candidate = client.decide(
    {
        "query": "Which maintenance window should an operator review?",
        "options": ["Saturday 02:00 UTC", "Sunday 02:00 UTC"],
    }
)
```

`VeritasAPIError` exposes `status_code` and `response_body` for non-2xx API
responses. Network failures, timeouts, invalid JSON, and non-object JSON raise
`VeritasTransportError`.

## Bind-related call pattern

`examples/webhook_bind.py` prepares a deliberately non-executing payload that
an external application could carry into its own reviewed bind workflow. Run
it without credentials:

```bash
PYTHONPATH=. python examples/webhook_bind.py
```

The example is not a production-certified integration and does not define a
new VERITAS endpoint. Use the deployed VERITAS contract and the documented
`WebhookBindAdapter` controls when implementing a real bind path.

## Security notes

- Do not commit API keys or include them in logs and error reports.
- Use HTTPS with certificate verification for non-local deployments.
- Treat decision and error payloads as potentially sensitive application data.
- Validate the deployed API contract and apply least-privilege credentials.
- Never treat a successful decision response as permission to perform a side
  effect; complete the governed Bind Boundary flow first.
