from __future__ import annotations

from types import SimpleNamespace

from veritas_os.scripts.cage_provider03_phase5d_runner import (
    ESCALATE_SCENARIO,
    _exposes_bind_receipt,
    _needs_human_review,
    _payload,
    _principal_hash,
)


def test_phase5d_payload_binds_fixed_escalate_scenario() -> None:
    payload = _payload(ESCALATE_SCENARIO)
    assert payload["veritas_scenario_name"] == "scenario_d_stale_sanctions_screening"
    assert payload["action"] == "aml_kyc_regulated_action"
    assert payload["action_context"] == {"amount": 1000, "symbol": "acct"}


def test_phase5d_human_review_marker_is_explicit() -> None:
    validation = SimpleNamespace(
        findings=[
            {
                "code": "provider_03.escalate",
                "needs_human_review": True,
            }
        ]
    )
    assert _needs_human_review(validation) is True


def test_phase5d_escalate_path_rejects_bind_receipt_exposure() -> None:
    clean = SimpleNamespace(findings=[{"code": "provider_03.escalate"}])
    leaked = SimpleNamespace(findings=[{"bind_receipt": {"bind_receipt_id": "bad"}}])
    assert _exposes_bind_receipt(clean) is False
    assert _exposes_bind_receipt(leaked) is True


def test_phase5d_principal_hash_is_deterministic_and_non_plaintext() -> None:
    urn = "urn:veritas:phase5d:reviewer:one"
    first = _principal_hash(urn)
    second = _principal_hash(urn)
    assert first == second
    assert first != urn
    assert len(first) == 64
