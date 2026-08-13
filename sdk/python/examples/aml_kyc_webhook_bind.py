"""Prepare a synthetic AML/KYC Decision Candidate for a bind review.

The SDK only calls VERITAS; ``/v1/decide`` does not authorize external side
effects. This example never contacts a webhook target. Any external execution
must separately cross the Bind Boundary, where ``WebhookBindAdapter`` remains
the reference external bind adapter pattern.

This example is not production certification, regulatory approval, or a live
bank integration. All case details are fictional and contain no customer data.
"""

import json
from typing import Any

from veritas_client import VeritasClient


def build_review_payload() -> dict[str, Any]:
    """Build a fictional AML/KYC review request with no customer data."""
    return {
        "query": (
            "Which review disposition should an analyst consider for this "
            "synthetic AML/KYC case?"
        ),
        "options": [
            "request_additional_documentation",
            "escalate_for_human_review",
            "record_no_further_action_candidate",
        ],
        "context": {
            "case_id": "synthetic-case-001",
            "risk_signals": [
                "synthetic_identity_mismatch",
                "synthetic_source_of_funds_review",
            ],
            "data_classification": "synthetic_example_only",
        },
    }


def request_review(client: VeritasClient) -> dict[str, Any]:
    """Call VERITAS for a Decision Candidate, not execution authority."""
    return client.decide(build_review_payload())


def prepare_bind_payload(decision: dict[str, Any]) -> dict[str, Any]:
    """Prepare, without sending, data for later Bind Boundary adjudication."""
    return {
        "decision_id": decision.get("decision_id"),
        "adapter_pattern": "WebhookBindAdapter",
        "target": "https://example.invalid/aml-kyc-review",
        "action_payload": {
            "case_id": "synthetic-case-001",
            "requested_operation": "create_human_review_task",
        },
        "execution_status": "not_executed",
        "requires_bind_adjudication": True,
    }


def main() -> None:
    """Display synthetic review and non-executing bind payloads locally."""
    review_payload = build_review_payload()
    bind_payload = prepare_bind_payload(
        {"decision_id": "replace-with-reviewed-decision-id"}
    )
    print(
        json.dumps(
            {"review_payload": review_payload, "bind_payload": bind_payload},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
