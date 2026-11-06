from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from veritas_os.security.tls_kex_execution import (
    COUNTER_NAMES,
    StaticDispatchManifest,
    StaticMappingManifest,
    TLSKexQualificationError,
    derive_security_counters,
    qualify_execution_chain,
)


def observation() -> dict[str, object]:
    return {
        "private_libctx": True,
        "property_query": "provider=test-a",
        "openssl_identity": "OpenSSL controlled-test-build",
        "private_runtime_profile": "PRIVATE_OSSL_LIB_CTX_V1",
        "provider_inventory": [{"name": "test-a", "build": "sha256:abc"}],
        "tls_group_candidate_count": 1,
        "tls_group_capability_profile": {
            "name": "TESTGROUP", "internal": "testgroup", "id": 65024,
            "algorithm": "TESTKEY", "security_bits": 128, "is_kem": False,
            "min_tls": 772, "max_tls": 0, "min_dtls": -1, "max_dtls": -1,
            "provider": "test-a",
        },
        "iana_group_name": "TESTGROUP",
        "iana_group_codepoint": 65024,
        "tls_group_algorithm": "TESTKEY",
        "tls_group_provider": "test-a",
        "keymgmt_candidate_count": 1,
        "keymgmt_provider": "test-a",
        "provider_code_identity": "test-a:sha256:abc",
        "operation_id": 11,
        "query_operation_name_present": True,
        "query_operation_name_result": "TESTDERIVE",
        "operation_type": "KEYEXCH",
        "operation_candidate_count": 1,
        "operation_provider": "test-a",
        "fetched_operation_provider": "test-a",
        "keymgmt_no_store": 0,
        "operation_no_store": 0,
        "keymgmt_dispatch_function_ids": [1, 2, 20],
        "operation_dispatch_function_ids": [1, 2, 3],
    }


def manifests(*, eligible: bool = True) -> tuple[StaticMappingManifest, list[StaticDispatchManifest]]:
    mapping = StaticMappingManifest(
        "test-a:sha256:abc", "TESTKEY", 11, "TESTDERIVE", "sha256:mapping", eligible
    )
    dispatch = [
        StaticDispatchManifest("test-a:sha256:abc", "KEYMGMT", "sha256:km", "provider=test-a", (1, 2, 20), "sha256:km-proof"),
        StaticDispatchManifest("test-a:sha256:abc", "KEYEXCH", "sha256:kex", "provider=test-a", (1, 2, 3), "sha256:kex-proof"),
    ]
    return mapping, dispatch


def qualify(data: dict[str, object] | None = None) -> dict[str, object]:
    mapping, dispatch = manifests()
    return qualify_execution_chain(data or observation(), mapping, dispatch)


def test_profile_and_execution_digest_are_deterministic_and_pointer_free() -> None:
    first = qualify()
    second = qualify(deepcopy(observation()))
    assert first == second
    assert first["normalized_operation_algorithm"] == "TESTDERIVE"
    assert re.fullmatch(r"[0-9a-f]{64}", str(first["execution_chain_digest"]))
    assert "0x" not in json.dumps(first)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tls_group_candidate_count", 0),
        ("tls_group_candidate_count", 2),
        ("keymgmt_candidate_count", 0),
        ("keymgmt_candidate_count", 2),
        ("operation_candidate_count", 0),
        ("operation_candidate_count", 2),
        ("keymgmt_no_store", 1),
        ("operation_no_store", 1),
    ],
)
def test_ambiguous_missing_or_noncacheable_selection_rejected(field: str, value: int) -> None:
    data = observation()
    data[field] = value
    with pytest.raises(TLSKexQualificationError):
        qualify(data)


@pytest.mark.parametrize("field", ["keymgmt_provider", "operation_provider", "fetched_operation_provider"])
def test_provider_split_rejected(field: str) -> None:
    data = observation()
    data[field] = "test-b"
    with pytest.raises(TLSKexQualificationError):
        qualify(data)


@pytest.mark.parametrize(("present", "result"), [(False, None), (True, None)])
def test_absent_or_null_query_falls_back_to_algorithm(present: bool, result: None) -> None:
    data = observation()
    data["query_operation_name_present"] = present
    data["query_operation_name_result"] = result
    mapping, dispatch = manifests()
    mapping = StaticMappingManifest("test-a:sha256:abc", "TESTKEY", 11, "TESTKEY", "sha256:fallback")
    profile = qualify_execution_chain(data, mapping, dispatch)
    assert profile["normalized_operation_algorithm"] == "TESTKEY"


def test_stateful_mapping_is_ineligible() -> None:
    mapping, dispatch = manifests(eligible=False)
    with pytest.raises(TLSKexQualificationError):
        qualify_execution_chain(observation(), mapping, dispatch)


def test_selected_kem_no_store_is_rejected() -> None:
    data = observation()
    data["operation_type"] = "KEM"
    data["operation_no_store"] = 1
    mapping, dispatch = manifests()
    dispatch.append(
        StaticDispatchManifest(
            "test-a:sha256:abc",
            "KEM",
            "sha256:kem",
            "provider=test-a",
            (1, 2, 3),
            "sha256:kem-proof",
        )
    )
    with pytest.raises(TLSKexQualificationError):
        qualify_execution_chain(data, mapping, dispatch)


def test_dispatch_drift_rejected() -> None:
    data = observation()
    data["operation_dispatch_function_ids"] = [1, 2, 4]
    with pytest.raises(TLSKexQualificationError):
        qualify(data)


def test_event_counters_are_derived_from_events() -> None:
    events = [
        {"event": "provider_query_operation", "operation_type": "KEYMGMT", "selected": True, "no_store": 1},
        {"event": "query_operation_name", "stateful_query_operation_name_acceptances": True, "P_bound_vs_runtime_OPALG_mismatches": True},
        {"event": "KEYEXCH_execution", "operation_type": "KEYEXCH", "unexpected_KEYEXCH_provider_executions": True, "provider_operation_dispatch_drifts": True},
    ]
    counters = derive_security_counters(events)
    assert set(counters) == set(COUNTER_NAMES)
    assert counters["noncacheable_selected_KEYMGMT_operations"] == 1
    assert counters["stateful_query_operation_name_acceptances"] == 1
    assert counters["P_bound_vs_runtime_OPALG_mismatches"] == 1
    assert counters["unexpected_KEYEXCH_provider_executions"] == 1
    assert counters["dynamic_operation_definition_acceptances"] == 0


def test_real_openssl_ec_resolves_to_ecdh() -> None:
    root = Path(__file__).parents[2]
    native = root / "native" / "tls_kex_qualifier"
    subprocess.run(["make", "clean", "all"], cwd=native, check=True)
    result = subprocess.run([str(native / "openssl_kex_probe")], check=True, text=True, capture_output=True)
    payload = json.loads(result.stdout)
    assert payload["private_libctx"] is True
    assert payload["property_query"] == "provider=default"
    assert payload["group_algorithm"] == "EC"
    assert payload["operation_algorithm"] == "ECDH"
    assert payload["keymgmt_no_store"] == 0
    assert payload["operation_no_store"] == 0
