"""Tests for the trusted public key provenance receipt schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "trusted_public_key_provenance_receipt.schema.json"
)
VALID_FINGERPRINT = "0123456789abcdef" * 4


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_receipt() -> dict[str, Any]:
    return {
        "receipt_type": "trusted_public_key_provenance",
        "algorithm": "Ed25519",
        "public_key_fingerprint_sha256": VALID_FINGERPRINT,
        "trust_channel": "operator_handoff",
        "received_at": "2026-06-09T00:00:00Z",
        "approved_by": "reviewer@example.com",
        "approval_reference": "ticket-or-vault-reference",
        "notes": "Public key received from out-of-band trust record.",
        "bundle_internal_key_used": False,
    }


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_load_schema(), format_checker=FormatChecker())


def _messages_for(receipt: dict[str, Any]) -> list[str]:
    return [error.message for error in _validator().iter_errors(receipt)]


def test_schema_loads_and_is_valid_draft_2020_12() -> None:
    schema = _load_schema()

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_valid_receipt_matches_schema() -> None:
    _validator().validate(_valid_receipt())


def test_required_fields_are_enforced() -> None:
    for field in _load_schema()["required"]:
        receipt = _valid_receipt()
        receipt.pop(field)

        messages = _messages_for(receipt)

        assert any(field in message and "required" in message for message in messages)


def test_public_key_fingerprint_must_be_64_lowercase_hex() -> None:
    invalid_values = [
        "0123456789abcdef" * 3,
        "0123456789abcdef" * 4 + "00",
        "0123456789ABCDEF" * 4,
        "g" * 64,
    ]

    for value in invalid_values:
        receipt = _valid_receipt()
        receipt["public_key_fingerprint_sha256"] = value

        messages = _messages_for(receipt)

        assert any("does not match" in message for message in messages)


def test_algorithm_requires_ed25519() -> None:
    receipt = _valid_receipt()
    receipt["algorithm"] = "RSA"

    messages = _messages_for(receipt)

    assert any("Ed25519" in message for message in messages)


def test_trust_channel_enum_rejects_unknown_values_unless_other() -> None:
    receipt = _valid_receipt()
    receipt["trust_channel"] = "chat_message"

    messages = _messages_for(receipt)

    assert any("not one of" in message for message in messages)

    receipt["trust_channel"] = "other"
    _validator().validate(receipt)


def test_bundle_internal_key_use_is_rejected() -> None:
    receipt = _valid_receipt()
    receipt["bundle_internal_key_used"] = True

    messages = _messages_for(receipt)

    assert any("False was expected" in message for message in messages)


def test_schema_description_documents_security_boundaries() -> None:
    description = _load_schema()["description"]

    expected_phrases = [
        "out-of-band trust record",
        "Evidence Bundle alone is not enough",
        "not regulatory certification",
        "not completed third-party audit approval",
    ]
    for phrase in expected_phrases:
        assert phrase in description
