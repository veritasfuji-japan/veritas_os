"""Prepare a reference payload for a separately governed webhook bind flow."""

import json
from typing import Any


def prepare_bind_payload(
    decision_id: str,
    target_url: str,
    action_payload: dict[str, Any],
) -> dict[str, Any]:
    """Prepare application data for review at a Bind Boundary.

    This helper neither adjudicates nor executes a bind. Integrators must map
    this data to their reviewed bind interface and production controls.
    """
    return {
        "decision_id": decision_id,
        "adapter": "webhook",
        "target_url": target_url,
        "action_payload": action_payload,
        "execution_status": "not_executed",
        "requires_bind_adjudication": True,
    }


def main() -> None:
    """Display a non-executing bind payload example."""
    payload = prepare_bind_payload(
        decision_id="replace-with-reviewed-decision-id",
        target_url="https://example.invalid/reviewed-webhook",
        action_payload={"operation": "schedule_maintenance"},
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
