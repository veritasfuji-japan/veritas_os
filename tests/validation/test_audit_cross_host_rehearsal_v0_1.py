"""Input and fail-closed controls for the cross-host verifier entrypoint."""
from __future__ import annotations

import json

import pytest

from scripts.validation.audit_cross_host_rehearsal_v0_1 import _load, run


def test_duplicate_json_rejected(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError, match="DUPLICATE_KEY"):
        _load(p)


def test_nonfinite_json_rejected(tmp_path):
    p = tmp_path / "nan.json"
    p.write_text('{"a":NaN}')
    with pytest.raises(ValueError, match="INVALID_JSON_CONSTANT"):
        _load(p)


def test_missing_json_rejected(tmp_path):
    with pytest.raises(ValueError):
        _load(tmp_path / "missing.json")


@pytest.mark.asyncio
async def test_missing_external_pins_fail_closed(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps({}))
    ca = tmp_path / "missing-ca.pem"
    args = dict(
        reference=p, receipt=p, endpoint="https://localhost/v1/audit/checkpoints/latest",
        expected_hostname="localhost", ca_bundle=ca,
        trusted_signer_public_key_hex="0" * 64, minimum_sequence=1,
    )
    assert await run(**args) == "EXTERNAL_TRUST_REQUIRED"
    ca.write_text("not a CA")
    args["trusted_signer_public_key_hex"] = "wrong"
    assert await run(**args) == "EXTERNAL_TRUST_REQUIRED"
    args["trusted_signer_public_key_hex"] = "0" * 64
    args["minimum_sequence"] = 0
    assert await run(**args) == "EXTERNAL_TRUST_REQUIRED"


@pytest.mark.asyncio
async def test_bad_endpoint_and_certificate_fail_closed(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text("{}")
    ca = tmp_path / "bad-ca.pem"
    ca.write_text("not a CA")
    args = dict(
        reference=p, receipt=p, endpoint="http://localhost/v1/audit/checkpoints/latest",
        expected_hostname="localhost", ca_bundle=ca,
        trusted_signer_public_key_hex="0" * 64, minimum_sequence=1,
    )
    assert await run(**args) == "REMOTE_ENDPOINT_INVALID"
    args["endpoint"] = "https://localhost/v1/audit/checkpoints/latest"
    assert await run(**args) == "REMOTE_ANCHOR_UNAVAILABLE"
