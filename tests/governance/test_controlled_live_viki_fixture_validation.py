"""Offline validation skeleton for controlled live V.I.K.I. fixture payloads."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "controlled_live_viki_payload_schema"

VALID_FIXTURES = [
    "valid_safe_proceed_v1alpha1.json",
    "valid_density_throttled_v1alpha1.json",
    "valid_algorithmic_humility_engaged_v1alpha1.json",
    "valid_deferral_engaged_v1alpha1.json",
]

EXPECTED_INVALID_FIXTURES = [
    "invalid_unknown_rsa_status_v1alpha1.json",
    "invalid_missing_request_id_v1alpha1.json",
    "invalid_missing_correlation_id_v1alpha1.json",
    "invalid_forbidden_chain_of_thought_v1alpha1.json",
    "invalid_secret_access_token_v1alpha1.json",
    "invalid_raw_kyc_record_v1alpha1.json",
    "invalid_naive_timestamp_v1alpha1.json",
    "invalid_payload_issued_at_future_skew_v1alpha1.json",
    "invalid_duplicate_request_id_scenario_a_v1alpha1.json",
    "invalid_duplicate_request_id_scenario_b_v1alpha1.json",
    "invalid_unsupported_schema_version.json",
]

EXPECTED_FIXTURES = set(VALID_FIXTURES + EXPECTED_INVALID_FIXTURES)

REQUIRED_FIELDS = {
    "schema_version",
    "rsa_status",
    "trigger_source",
    "timestamp",
    "request_id",
    "correlation_id",
    "payload_issued_at",
}

ACCEPTED_RSA_STATUS = {
    "SAFE_PROCEED",
    "DENSITY_THROTTLED",
    "ALGORITHMIC_HUMILITY_ENGAGED",
    "DEFERRAL_ENGAGED",
}

FORBIDDEN_REASONING_FIELDS = {
    "chain_of_thought",
    "hidden_model_state",
    "raw_llm_reasoning",
    "raw_viki_reasoning",
}

SECRET_LIKE_FIELDS = {
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
    "webhook_secret",
    "secrets",
    "credentials",
}

REGULATED_DATA_FIELDS = {
    "raw_kyc_record",
    "customer_pii",
    "unredacted_regulated_data",
}

FORBIDDEN_FIELDS = FORBIDDEN_REASONING_FIELDS | SECRET_LIKE_FIELDS | REGULATED_DATA_FIELDS


def _load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)
    assert isinstance(payload, dict)
    return payload


def _load_all_fixtures() -> dict[str, dict]:
    return {name: _load_fixture(name) for name in sorted(EXPECTED_FIXTURES)}


def _is_timezone_aware_timestamp(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _contains_forbidden_field(payload: dict) -> bool:
    return any(field in payload for field in FORBIDDEN_REASONING_FIELDS)


def _contains_secret_like_field(payload: dict) -> bool:
    return any(field in payload for field in SECRET_LIKE_FIELDS)


def _contains_regulated_data_field(payload: dict) -> bool:
    return any(field in payload for field in REGULATED_DATA_FIELDS)


def _classify_fixture(
    name: str,
    payload: dict,
    *,
    seen_request_ids: dict[str, str] | None = None,
) -> str:
    if payload.get("schema_version") != "v1alpha1":
        return "FIXTURE_UNSUPPORTED_SCHEMA_VERSION"

    missing_fields = [field for field in REQUIRED_FIELDS if not payload.get(field)]
    if missing_fields:
        return "FIXTURE_MISSING_REQUIRED_FIELD"

    if payload.get("rsa_status") not in ACCEPTED_RSA_STATUS:
        return "FIXTURE_UNKNOWN_RSA_STATUS"

    if not _is_timezone_aware_timestamp(payload.get("timestamp", "")):
        return "FIXTURE_INVALID_TIMESTAMP"
    if not _is_timezone_aware_timestamp(payload.get("payload_issued_at", "")):
        return "FIXTURE_INVALID_TIMESTAMP"

    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    payload_issued_at = datetime.fromisoformat(payload["payload_issued_at"].replace("Z", "+00:00"))
    if payload_issued_at > timestamp:
        return "FIXTURE_INVALID_TIMESTAMP"

    if _contains_regulated_data_field(payload):
        return "FIXTURE_REGULATED_DATA_PRESENT"

    if _contains_secret_like_field(payload):
        return "FIXTURE_SECRET_LIKE_VALUE_PRESENT"

    if _contains_forbidden_field(payload):
        return "FIXTURE_FORBIDDEN_FIELD_PRESENT"

    if seen_request_ids is not None:
        request_id = payload["request_id"]
        correlation_id = payload["correlation_id"]
        if request_id in seen_request_ids and seen_request_ids[request_id] != correlation_id:
            return "FIXTURE_REPLAY_SCENARIO_DUPLICATE"
        seen_request_ids[request_id] = correlation_id

    return "FIXTURE_VALID"


def test_controlled_live_fixture_inventory_is_exact() -> None:
    assert FIXTURE_DIR.exists()
    json_files = {path.name for path in FIXTURE_DIR.glob("*.json")}
    assert EXPECTED_FIXTURES.issubset(json_files)
    assert not (EXPECTED_FIXTURES - json_files)
    assert json_files == EXPECTED_FIXTURES


def test_controlled_live_fixtures_are_valid_json_objects() -> None:
    fixtures = _load_all_fixtures()
    assert fixtures
    for name, payload in fixtures.items():
        assert isinstance(payload, dict), name
        assert not isinstance(payload, list), name
        assert payload, name


def test_valid_controlled_live_fixtures_match_schema_skeleton() -> None:
    fixtures = _load_all_fixtures()
    for name in VALID_FIXTURES:
        payload = fixtures[name]
        assert _classify_fixture(name, payload) == "FIXTURE_VALID"
        assert payload["schema_version"] == "v1alpha1"
        assert payload["rsa_status"] in ACCEPTED_RSA_STATUS
        for field in REQUIRED_FIELDS:
            assert field in payload
            assert isinstance(payload[field], str)
            assert payload[field].strip()
        assert _is_timezone_aware_timestamp(payload["timestamp"])
        assert _is_timezone_aware_timestamp(payload["payload_issued_at"])
        assert not _contains_forbidden_field(payload)
        assert not _contains_secret_like_field(payload)
        assert not _contains_regulated_data_field(payload)


def test_invalid_controlled_live_fixtures_classify_deterministically() -> None:
    expected_classifications = {
        "invalid_unknown_rsa_status_v1alpha1.json": "FIXTURE_UNKNOWN_RSA_STATUS",
        "invalid_missing_request_id_v1alpha1.json": "FIXTURE_MISSING_REQUIRED_FIELD",
        "invalid_missing_correlation_id_v1alpha1.json": "FIXTURE_MISSING_REQUIRED_FIELD",
        "invalid_forbidden_chain_of_thought_v1alpha1.json": "FIXTURE_FORBIDDEN_FIELD_PRESENT",
        "invalid_secret_access_token_v1alpha1.json": "FIXTURE_SECRET_LIKE_VALUE_PRESENT",
        "invalid_raw_kyc_record_v1alpha1.json": "FIXTURE_REGULATED_DATA_PRESENT",
        "invalid_naive_timestamp_v1alpha1.json": "FIXTURE_INVALID_TIMESTAMP",
        "invalid_payload_issued_at_future_skew_v1alpha1.json": "FIXTURE_INVALID_TIMESTAMP",
        "invalid_unsupported_schema_version.json": "FIXTURE_UNSUPPORTED_SCHEMA_VERSION",
    }
    fixtures = _load_all_fixtures()
    for name, expected in expected_classifications.items():
        assert _classify_fixture(name, fixtures[name]) == expected


def test_duplicate_request_id_scenario_is_detected() -> None:
    scenario_a = _load_fixture("invalid_duplicate_request_id_scenario_a_v1alpha1.json")
    scenario_b = _load_fixture("invalid_duplicate_request_id_scenario_b_v1alpha1.json")

    assert scenario_a["request_id"] == scenario_b["request_id"]
    assert scenario_a["correlation_id"] != scenario_b["correlation_id"]

    seen_request_ids: dict[str, str] = {}
    assert (
        _classify_fixture(
            "invalid_duplicate_request_id_scenario_a_v1alpha1.json",
            scenario_a,
            seen_request_ids=seen_request_ids,
        )
        == "FIXTURE_VALID"
    )
    assert (
        _classify_fixture(
            "invalid_duplicate_request_id_scenario_b_v1alpha1.json",
            scenario_b,
            seen_request_ids=seen_request_ids,
        )
        == "FIXTURE_REPLAY_SCENARIO_DUPLICATE"
    )


def test_forbidden_fields_are_not_allowed_in_valid_fixtures() -> None:
    fixtures = _load_all_fixtures()
    for name in VALID_FIXTURES:
        assert not (FORBIDDEN_FIELDS & set(fixtures[name].keys())), name

    assert (
        _classify_fixture(
            "invalid_forbidden_chain_of_thought_v1alpha1.json",
            fixtures["invalid_forbidden_chain_of_thought_v1alpha1.json"],
        )
        == "FIXTURE_FORBIDDEN_FIELD_PRESENT"
    )
    assert (
        _classify_fixture(
            "invalid_secret_access_token_v1alpha1.json",
            fixtures["invalid_secret_access_token_v1alpha1.json"],
        )
        == "FIXTURE_SECRET_LIKE_VALUE_PRESENT"
    )
    assert (
        _classify_fixture(
            "invalid_raw_kyc_record_v1alpha1.json",
            fixtures["invalid_raw_kyc_record_v1alpha1.json"],
        )
        == "FIXTURE_REGULATED_DATA_PRESENT"
    )


def test_fixture_validation_uses_static_offline_inputs_only() -> None:
    source_text = Path(__file__).read_text(encoding="utf-8")
    assert "tests/fixtures/controlled_live_viki_payload_schema" in source_text
    forbidden_imports = ("requests", "httpx", "urllib", "socket")
    assert all(f"import {name}" not in source_text for name in forbidden_imports)
