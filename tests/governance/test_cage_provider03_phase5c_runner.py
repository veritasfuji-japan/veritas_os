from __future__ import annotations

from types import SimpleNamespace

import pytest

from veritas_os.scripts.cage_provider03_phase5c_runner import (
    extract_bind_receipt,
    veritas_bind_receipt_hash_valid,
)
from veritas_os.security.hash import sha256_of_canonical_json


def _receipt() -> dict[str, str]:
    body = {
        "bind_receipt_id": "bind::phase5c-test",
        "action_contract_id": "contract::test",
        "authority_evidence_id": "authority::test",
        "authority_evidence_hash": "a" * 64,
        "commit_boundary_result": "commit",
    }
    return {**body, "bind_receipt_hash": sha256_of_canonical_json(body)}


def test_extract_bind_receipt_requires_admitted_result() -> None:
    result = SimpleNamespace(admitted=False, findings=[{"bind_receipt": _receipt()}])
    with pytest.raises(RuntimeError, match="requires an admitted"):
        extract_bind_receipt(result)


def test_extract_and_verify_bind_receipt_hash_domain() -> None:
    receipt = _receipt()
    result = SimpleNamespace(admitted=True, findings=[{"bind_receipt": receipt}])

    extracted = extract_bind_receipt(result)

    assert extracted == receipt
    assert veritas_bind_receipt_hash_valid(extracted) is True

    tampered = dict(extracted)
    tampered["authority_evidence_id"] = "authority::tampered"
    assert veritas_bind_receipt_hash_valid(tampered) is False
