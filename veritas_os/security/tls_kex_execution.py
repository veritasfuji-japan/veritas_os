"""Fail-closed semantic boundary for native TLS key-exchange qualification.

This module does not participate in the sandbox transport.  It canonicalizes
observations made by the separately compiled OpenSSL probe and requires the
reviewed strong-v1 stability manifests before issuing qualification evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from veritas_os.security.hash import sha256_of_canonical_json


PROFILE_VERSION = "TLS13KeyExchangeExecutionProfileV1"
MAPPING_VERSION = "KEYMGMT_OPERATION_NAME_STABILITY_V1"
DISPATCH_VERSION = "STATIC_CACHEABLE_DISPATCH_V1"


class TLSKexQualificationError(RuntimeError):
    """Raised when strong qualification cannot be established."""


@dataclass(frozen=True)
class StaticMappingManifest:
    """Human-reviewed assertion that an operation-name mapping is static."""

    provider_code_identity: str
    algorithm: str
    operation_id: int
    expected_operation_algorithm: str
    proof_manifest_digest: str
    eligible: bool = True

    def profile(self) -> dict[str, Any]:
        return {
            "mapping_profile_version": MAPPING_VERSION,
            "stability_profile": "STATIC_PURE_MAPPING_V1"
            if self.eligible
            else "NOT_ELIGIBLE_FOR_STATIC_PURE_MAPPING_V1",
            **self.__dict__,
        }


@dataclass(frozen=True)
class StaticDispatchManifest:
    """Human-reviewed assertion for one cacheable provider dispatch."""

    provider_code_identity: str
    operation_type: str
    algorithm_semantic_digest: str
    property_profile: str
    dispatch_function_ids: tuple[int, ...]
    proof_manifest_digest: str

    def profile(self) -> dict[str, Any]:
        return {"profile_version": DISPATCH_VERSION, **self.__dict__}


def _exactly_one(value: Any, label: str) -> None:
    if value != 1:
        raise TLSKexQualificationError(f"{label} candidate count must be 1, got {value}")


def qualify_execution_chain(
    observation: Mapping[str, Any],
    mapping_manifest: StaticMappingManifest,
    dispatch_manifests: Iterable[StaticDispatchManifest],
) -> dict[str, Any]:
    """Validate an OpenSSL observation and return its immutable canonical profile."""
    if not observation.get("private_libctx") or not observation.get("property_query"):
        raise TLSKexQualificationError("private libctx and non-empty property query required")
    _exactly_one(observation.get("tls_group_candidate_count"), "TLS-GROUP")
    _exactly_one(observation.get("keymgmt_candidate_count"), "KEYMGMT")
    _exactly_one(observation.get("operation_candidate_count"), "OPALG")

    algorithm = str(observation["tls_group_algorithm"])
    raw_result = observation.get("query_operation_name_result")
    operation_algorithm = str(raw_result or algorithm)
    provider = observation["tls_group_provider"]
    if not (
        provider
        == observation["keymgmt_provider"]
        == observation["operation_provider"]
        == observation.get("fetched_operation_provider")
    ):
        raise TLSKexQualificationError("provider equality or preflight fetch failed")
    if observation.get("keymgmt_no_store") != 0:
        raise TLSKexQualificationError("selected KEYMGMT is non-cacheable")
    if observation.get("operation_no_store") != 0:
        raise TLSKexQualificationError("selected operation is non-cacheable")
    if (
        not mapping_manifest.eligible
        or mapping_manifest.provider_code_identity != observation["provider_code_identity"]
        or mapping_manifest.algorithm != algorithm
        or mapping_manifest.operation_id != observation["operation_id"]
        or mapping_manifest.expected_operation_algorithm != operation_algorithm
    ):
        raise TLSKexQualificationError("reviewed static mapping manifest mismatch")

    dispatches = {item.operation_type: item for item in dispatch_manifests}
    operation_type = str(observation["operation_type"])
    for selected_type, ids_key in (
        ("KEYMGMT", "keymgmt_dispatch_function_ids"),
        (operation_type, "operation_dispatch_function_ids"),
    ):
        manifest = dispatches.get(selected_type)
        if (
            manifest is None
            or manifest.provider_code_identity
            != observation["provider_code_identity"]
            or manifest.property_profile != observation["property_query"]
            or tuple(observation[ids_key]) != manifest.dispatch_function_ids
        ):
            raise TLSKexQualificationError(
                f"reviewed static dispatch manifest mismatch: {selected_type}"
            )

    mapping_profile = mapping_manifest.profile()
    mapping_digest = sha256_of_canonical_json(mapping_profile)
    keymgmt_dispatch = dispatches["KEYMGMT"].profile()
    operation_dispatch = dispatches[operation_type].profile()
    profile = {
        "profile_version": PROFILE_VERSION,
        "iana_group_name": observation["iana_group_name"],
        "iana_group_codepoint": observation["iana_group_codepoint"],
        "property_query": observation["property_query"],
        "openssl_identity": observation["openssl_identity"],
        "private_runtime_profile": observation["private_runtime_profile"],
        "provider_inventory_digest": sha256_of_canonical_json(
            observation["provider_inventory"]
        ),
        "tls_group_capability_profile": observation["tls_group_capability_profile"],
        "tls_group_algorithm": algorithm,
        "keymgmt_provider_code_identity": observation["provider_code_identity"],
        "keymgmt_candidate_count": 1,
        "operation_id": observation["operation_id"],
        "query_operation_name_present": observation[
            "query_operation_name_present"
        ],
        "query_operation_name_result": raw_result,
        "normalized_operation_algorithm": operation_algorithm,
        "algorithm_operation_mapping_digest": mapping_digest,
        "operation_name_stability_profile": mapping_profile,
        "keymgmt_no_store": 0,
        "keymgmt_dispatch_semantic_digest": sha256_of_canonical_json(
            keymgmt_dispatch
        ),
        "operation_type": operation_type,
        "operation_candidate_count": 1,
        "operation_provider_code_identity": observation["provider_code_identity"],
        "operation_no_store": 0,
        "operation_dispatch_semantic_digest": sha256_of_canonical_json(
            operation_dispatch
        ),
        "all_provider_equality": True,
    }
    profile["execution_chain_digest"] = sha256_of_canonical_json(profile)
    return profile


COUNTER_NAMES = (
    "noncacheable_selected_KEYMGMT_operations",
    "noncacheable_selected_KEYEXCH_operations",
    "noncacheable_selected_KEM_operations",
    "provider_operation_dispatch_drifts",
    "qualification_vs_runtime_dispatch_mismatches",
    "dynamic_operation_definition_acceptances",
    "stateful_query_operation_name_acceptances",
    "P_bound_vs_runtime_OPALG_mismatches",
    "P_bound_vs_actual_operation_implementation_mismatches",
    "unexpected_KEYEXCH_provider_executions",
    "unexpected_KEM_provider_executions",
)


def derive_security_counters(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Derive strong-profile counters solely from inspected provider events."""
    counters = {name: 0 for name in COUNTER_NAMES}
    for event in events:
        operation = event.get("operation_type")
        if event.get("selected") and event.get("no_store") == 1:
            key = f"noncacheable_selected_{operation}_operations"
            if key in counters:
                counters[key] += 1
        for name in COUNTER_NAMES[3:]:
            if event.get(name) is True:
                counters[name] += 1
    return counters
