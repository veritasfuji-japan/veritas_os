"""Behavior proof for the minimal separate_store_readonly_v1 resolver."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from veritas_os.audit.observable_digest_failure_codes import (
    ObservableDigestFailurePredicate,
)
from veritas_os.audit.observable_digest_resolver import (
    ImmutableSeparateStoreSnapshot,
    ObservableDigestResolverRequest,
    ResolverSemanticGuarantees,
    SeparateStoreReadonlyProfile,
    resolve_separate_store_readonly_v1,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "veritas_os" / "audit" / "observable_digest_resolver.py"

CALLER_A = "sha256:" + "a" * 64
CALLER_B = "sha256:" + "b" * 64
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64
REQUESTED_AT = "2026-09-28T05:00:00Z"
OBSERVED_AT = "2026-09-28T05:00:01Z"


def _profile() -> SeparateStoreReadonlyProfile:
    return SeparateStoreReadonlyProfile(
        resolver_id="resolver-separate-store-v1",
        namespace="digests",
        allowed_caller_id_hashes=(CALLER_A,),
    )


def _request(
    locator: str = "separate_store://digests/wat-5",
    *,
    caller_id_hash: str = CALLER_A,
    resolver_profile: str = "separate_store_readonly_v1",
) -> ObservableDigestResolverRequest:
    return ObservableDigestResolverRequest(
        request_id="req-1",
        locator=locator,
        caller_id_hash=caller_id_hash,
        requested_at=REQUESTED_AT,
        resolver_profile=resolver_profile,
    )


def _snapshot(
    digest: str = DIGEST_A,
) -> ImmutableSeparateStoreSnapshot:
    return ImmutableSeparateStoreSnapshot.from_mapping(
        {
            "separate_store://digests/wat-5": {
                "resolved_digest": digest,
                "record_version": "1",
            }
        }
    )


def _resolve(
    *,
    request: ObservableDigestResolverRequest | None = None,
    profile: SeparateStoreReadonlyProfile | None = None,
    snapshot: ImmutableSeparateStoreSnapshot | None = None,
):
    return resolve_separate_store_readonly_v1(
        request=request or _request(),
        profile=profile or _profile(),
        snapshot=snapshot or _snapshot(),
        observed_at=OBSERVED_AT,
    )


def test_valid_exact_locator_resolves_exact_stored_digest() -> None:
    resolution = _resolve()

    assert resolution.result.resolution_state == "RESOLVED"
    assert resolution.result.resolved_digest == DIGEST_A
    assert resolution.result.failure_predicates == ()
    assert resolution.result.evidence_ref is None
    assert resolution.result.to_contract_dict()["semantic_guarantees"] == {
        "authority_created": False,
        "execution_permission_changed": False,
        "digest_match_asserted": False,
        "boundary_validation_asserted": False,
        "uncertainty_erased": False,
        "remediation_executed": False,
    }


def test_internal_observation_binds_four_proof_dimensions() -> None:
    resolution = _resolve()
    observation = resolution.observation

    assert observation.request_id == "req-1"
    assert observation.locator == "separate_store://digests/wat-5"
    assert observation.resolver_profile == "separate_store_readonly_v1"
    assert observation.resolver_id == "resolver-separate-store-v1"
    assert observation.caller_id_hash == CALLER_A
    assert observation.access_scope == "digests"
    assert observation.observed_at == OBSERVED_AT
    assert observation.lookup_outcome == "RESOLVED"
    assert observation.request_hash.startswith("sha256:")
    assert observation.profile_hash.startswith("sha256:")
    assert observation.snapshot_hash.startswith("sha256:")
    assert observation.observation_hash.startswith("sha256:")


def test_empty_locator_is_rejected_before_contract_valid_runtime_request() -> None:
    with pytest.raises(ValueError, match="locator must be non-empty"):
        ObservableDigestResolverRequest(
            request_id="req-1",
            locator="",
            caller_id_hash=CALLER_A,
            requested_at=REQUESTED_AT,
            resolver_profile="separate_store_readonly_v1",
        )


@pytest.mark.parametrize(
    "locator",
    [
        "https://example.test/digest",
        "SEPARATE_STORE://digests/wat-5",
        "separate_store://digests/wat%2D5",
        "separate_store://digests/wat-5?x=1",
        "separate_store://digests/wat-5#frag",
        "separate_store://user@digests/wat-5",
        "separate_store://digests/./wat-5",
        "separate_store://digests/../wat-5",
        "separate_store://digests//wat-5",
        "separate_store://digests/ワット",
        " separate_store://digests/wat-5",
        "separate_store://digests/wat-5 ",
    ],
)
def test_noncanonical_or_unsupported_locator_fails_closed(locator: str) -> None:
    resolution = _resolve(request=_request(locator))

    assert resolution.result.resolution_state == "UNRESOLVED"
    assert resolution.result.resolved_digest is None
    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.LOCATOR_MALFORMED,
    )


def test_overlength_locator_fails_closed() -> None:
    locator = "separate_store://digests/" + ("a" * 480)
    assert len(locator) > 500

    resolution = _resolve(request=_request(locator))

    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.LOCATOR_MALFORMED,
    )


def test_unauthorized_caller_fails_before_snapshot_lookup() -> None:
    with patch.object(
        ImmutableSeparateStoreSnapshot,
        "lookup_exact",
        side_effect=AssertionError("snapshot lookup must not occur"),
    ):
        resolution = _resolve(request=_request(caller_id_hash=CALLER_B))

    assert resolution.result.resolution_state == "UNRESOLVED"
    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.AUTHZ_DENIED,
    )


def test_cross_namespace_fails_before_snapshot_lookup() -> None:
    request = _request("separate_store://other/wat-5")
    with patch.object(
        ImmutableSeparateStoreSnapshot,
        "lookup_exact",
        side_effect=AssertionError("snapshot lookup must not occur"),
    ):
        resolution = _resolve(request=request)

    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.AUTHZ_DENIED,
    )


def test_missing_exact_key_is_resolution_failed() -> None:
    resolution = _resolve(
        request=_request("separate_store://digests/missing"),
    )

    assert resolution.result.resolution_state == "UNRESOLVED"
    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
    )


@pytest.mark.parametrize(
    "record",
    [
        {"resolved_digest": DIGEST_A},
        {"record_version": "1"},
        {"resolved_digest": DIGEST_A, "record_version": "2"},
        {"resolved_digest": "sha256:ABC", "record_version": "1"},
        {
            "resolved_digest": DIGEST_A,
            "record_version": "1",
            "unexpected": "field",
        },
    ],
)
def test_invalid_typed_record_is_schema_mismatch(record: dict[str, object]) -> None:
    snapshot = ImmutableSeparateStoreSnapshot.from_mapping(
        {"separate_store://digests/wat-5": record}
    )

    resolution = _resolve(snapshot=snapshot)

    assert resolution.result.resolution_state == "UNRESOLVED"
    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.SCHEMA_MISMATCH,
    )


def test_profile_mismatch_is_schema_mismatch() -> None:
    resolution = _resolve(
        request=_request(resolver_profile="different_profile"),
    )

    assert resolution.result.failure_predicates == (
        ObservableDigestFailurePredicate.SCHEMA_MISMATCH,
    )


def test_snapshot_construction_order_does_not_change_identity_or_result() -> None:
    left = ImmutableSeparateStoreSnapshot.from_mapping(
        {
            "separate_store://digests/z": {
                "resolved_digest": DIGEST_B,
                "record_version": "1",
            },
            "separate_store://digests/wat-5": {
                "resolved_digest": DIGEST_A,
                "record_version": "1",
            },
        }
    )
    right = ImmutableSeparateStoreSnapshot.from_mapping(
        {
            "separate_store://digests/wat-5": {
                "record_version": "1",
                "resolved_digest": DIGEST_A,
            },
            "separate_store://digests/z": {
                "record_version": "1",
                "resolved_digest": DIGEST_B,
            },
        }
    )

    left_resolution = _resolve(snapshot=left)
    right_resolution = _resolve(snapshot=right)

    assert left.snapshot_hash == right.snapshot_hash
    assert left_resolution.to_canonical_json() == right_resolution.to_canonical_json()


def test_same_frozen_inputs_are_byte_equivalent() -> None:
    first = _resolve()
    second = _resolve()

    assert first.to_canonical_json().encode("utf-8") == second.to_canonical_json().encode(
        "utf-8"
    )
    assert first.observation.observation_hash == second.observation.observation_hash


def test_caller_owned_mapping_mutation_cannot_change_frozen_snapshot() -> None:
    raw_record: dict[str, object] = {
        "resolved_digest": DIGEST_A,
        "record_version": "1",
    }
    raw_snapshot: dict[str, object] = {
        "separate_store://digests/wat-5": raw_record,
    }
    snapshot = ImmutableSeparateStoreSnapshot.from_mapping(raw_snapshot)

    raw_record["resolved_digest"] = DIGEST_B
    raw_snapshot["separate_store://digests/new"] = {
        "resolved_digest": DIGEST_B,
        "record_version": "1",
    }

    resolution = _resolve(snapshot=snapshot)

    assert resolution.result.resolved_digest == DIGEST_A
    assert snapshot.lookup_exact("separate_store://digests/new") is None


def test_frozen_profile_and_snapshot_cannot_be_reassigned() -> None:
    profile = _profile()
    snapshot = _snapshot()

    with pytest.raises(FrozenInstanceError):
        profile.namespace = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.entries = ()  # type: ignore[misc]


def test_monotonic_evidence_degradation_never_strengthens_result() -> None:
    resolved = _resolve()
    unauthorized = _resolve(request=_request(caller_id_hash=CALLER_B))
    malformed = _resolve(request=_request("separate_store://digests/../wat-5"))
    missing = _resolve(request=_request("separate_store://digests/missing"))
    bad_record = _resolve(
        snapshot=ImmutableSeparateStoreSnapshot.from_mapping(
            {
                "separate_store://digests/wat-5": {
                    "resolved_digest": "bad",
                    "record_version": "1",
                }
            }
        )
    )

    assert resolved.result.resolution_state == "RESOLVED"
    for degraded in (unauthorized, malformed, missing, bad_record):
        assert degraded.result.resolution_state == "UNRESOLVED"
        assert degraded.result.resolved_digest is None
        assert degraded.result.semantic_guarantees == ResolverSemanticGuarantees()


def test_requested_at_is_not_silently_promoted_to_freshness_claim() -> None:
    future_request = ObservableDigestResolverRequest(
        request_id="req-future",
        locator="separate_store://digests/wat-5",
        caller_id_hash=CALLER_A,
        requested_at="2099-01-01T00:00:00Z",
        resolver_profile="separate_store_readonly_v1",
    )

    resolution = _resolve(request=future_request)

    assert resolution.result.resolution_state == "RESOLVED"
    assert resolution.result.semantic_guarantees.digest_match_asserted is False
    assert resolution.result.semantic_guarantees.boundary_validation_asserted is False
    assert resolution.result.semantic_guarantees.execution_permission_changed is False


def test_observed_at_must_be_explicit_utc_z() -> None:
    with pytest.raises(ValueError, match="observed_at must be ISO8601 UTC ending in Z"):
        resolve_separate_store_readonly_v1(
            request=_request(),
            profile=_profile(),
            snapshot=_snapshot(),
            observed_at="2026-09-28T05:00:01+00:00",
        )


def test_initial_profile_source_has_no_external_io_imports() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "boto3",
            "http",
            "httpx",
            "os",
            "pathlib",
            "psycopg",
            "requests",
            "socket",
            "sqlite3",
            "subprocess",
            "urllib",
        }
    )


def test_initial_profile_never_emits_unknown_transient() -> None:
    cases = [
        _resolve(),
        _resolve(request=_request(caller_id_hash=CALLER_B)),
        _resolve(request=_request("separate_store://digests/missing")),
        _resolve(request=_request("https://example.test/x")),
        _resolve(
            snapshot=ImmutableSeparateStoreSnapshot.from_mapping(
                {
                    "separate_store://digests/wat-5": {
                        "resolved_digest": "bad",
                        "record_version": "1",
                    }
                }
            )
        ),
    ]

    for resolution in cases:
        assert ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT not in (
            resolution.result.failure_predicates
        )


def test_result_cannot_be_constructed_with_amplified_semantic_guarantees() -> None:
    with pytest.raises(
        ValueError,
        match="resolver semantic guarantees are hard-false invariants",
    ):
        ResolverSemanticGuarantees(authority_created=True)


def test_snapshot_rejects_noncanonical_keys_and_is_bounded() -> None:
    with pytest.raises(ValueError, match="snapshot locators must already be canonical"):
        ImmutableSeparateStoreSnapshot.from_mapping(
            {
                "separate_store://digests/../x": {
                    "resolved_digest": DIGEST_A,
                    "record_version": "1",
                }
            }
        )
