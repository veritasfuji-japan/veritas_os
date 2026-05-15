"""Thin sandbox-only RSA ↔ VERITAS end-to-end harness.

This harness is for deterministic sandbox demonstration only.
It is not a production AML/KYC compliance implementation, not regulatory
approval evidence, not third-party certification, and not legal advice.
No real regulated data is used.

RSA remains external upstream context; VERITAS core governance remains
separate and only consumes the static payload to produce downstream
continuation and audit output.
"""

from __future__ import annotations

import json

from veritas_os.governance.rsa_sandbox_receiver import (
    RSASandboxPayload,
    evaluate_rsa_sandbox_signal,
)


def run_rsa_veritas_e2e_harness() -> dict[str, dict[str, str]]:
    """Run the documented static-payload sandbox flow and return deterministic output."""
    payload_dict = {
        "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
        "trigger_source": "SRC_Incomplete_Context",
        "original_llm_intent": "Recommend_Transaction_Approval",
        "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
        "timestamp": "2026-10-25T09:15:30Z",
    }

    payload = RSASandboxPayload(**payload_dict)
    result = evaluate_rsa_sandbox_signal(payload)

    return {
        "veritas_decision": result["veritas_decision"],
        "audit_entry": result["audit_entry"],
    }


if __name__ == "__main__":
    print(
        json.dumps(
            run_rsa_veritas_e2e_harness(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
