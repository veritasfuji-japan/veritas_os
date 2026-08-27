"""Canonical verified source-gate context for Real Bind governance."""

from __future__ import annotations

from typing import Any

from veritas_os.policy.live_adapter_bind_authorization_codec import _digest
from veritas_os.policy.live_adapter_bind_authorization_contracts import DOMAINS
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)


def derive_verified_real_bind_context_hash(source_gate_review_packet: Any) -> str:
    """Verify a Real Bind source gate and derive its canonical context hash.

    The verification boundary is deliberately part of this helper so callers
    cannot derive an approval context from caller-declared or stale gate fields.

    Args:
        source_gate_review_packet: Candidate production source-gate packet.

    Returns:
        The canonical Real Bind context digest for the verified packet.

    Raises:
        ValueError: If the packet is malformed or fails integrity verification.
    """
    source = verify_live_adapter_dry_run_bind_authorization_gate_review_packet(
        source_gate_review_packet
    )
    return _digest(
        DOMAINS["bind_context"],
        {
            "source_gate_review_hash": (
                source.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
            "execution_intent_id": source.execution_intent_id,
            "execution_intent_hash": source.execution_intent_hash,
            "adapter_contract_id": source.adapter_contract_id,
            "adapter_contract_hash": source.adapter_contract_hash,
            "endpoint_identity_binding_digest": (
                source.endpoint_identity_binding_digest
            ),
            "credential_reference_digest": source.credential_reference_digest,
            "credential_scope_binding_digest": (
                source.credential_scope_binding_digest
            ),
        },
    )


__all__ = ["derive_verified_real_bind_context_hash"]
