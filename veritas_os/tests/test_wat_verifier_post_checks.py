"""Regression tests for shared WAT verifier post-validation checks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from veritas_os.security.wat_token import compute_observable_digests
from veritas_os.security.wat_verifier import validate_local


BASE_CLAIMS: dict[str, Any] = {
    "psid_full": "psid",
    "action_digest": "action",
    "observable_digest": "obs",
    "issuance_ts": 1000,
    "expiry_ts": 2000,
    "nonce": "nonce",
    "session_id": "session",
}


def _run_case(
    *,
    claims: dict[str, Any],
    observable_refs_local: list[dict[str, str]] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    config = {"signature_verifier": lambda _claims, _sig: True}
    config.update(kwargs.pop("config", {}))
    return validate_local(
        signed_wat={"claims": claims, "signature": "sig"},
        psid_full_local="psid",
        action_digest_local="action",
        observable_refs_local=observable_refs_local,
        observable_digest_local="obs",
        issuance_ts_local=kwargs.pop("issuance_ts_local", 1000),
        expiry_ts_local=kwargs.pop("expiry_ts_local", 2000),
        execution_nonce="nonce",
        session_id="session",
        revocation_state=kwargs.pop("revocation_state", None),
        now_ts=kwargs.pop("now_ts", 1500),
        config=config,
        replay_cache=kwargs.pop("replay_cache", set()),
    )


def _paired_results(*, claims: dict[str, Any], **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    non_list = _run_case(claims=deepcopy(claims), observable_refs_local=None, **kwargs)
    observable_refs = [{"id": "obs-1", "value": "x"}]
    list_claims = deepcopy(claims)
    list_claims["observable_digest_list"] = compute_observable_digests(observable_refs)
    with_list = _run_case(claims=list_claims, observable_refs_local=observable_refs, **kwargs)
    return non_list, with_list


def _assert_post_check_parity(
    non_list: dict[str, Any],
    with_list: dict[str, Any],
    *,
    expected_status: str,
    expected_failure_type: str | None,
) -> None:
    assert (
        non_list["validation_status"]
        == with_list["validation_status"]
        == expected_status
    )
    assert non_list["failure_type"] == with_list["failure_type"] == expected_failure_type
    assert non_list["drift_vector"] == with_list["drift_vector"]
    assert (
        non_list["admissibility_state"] == with_list["admissibility_state"]
    )


def test_post_checks_parity_between_observable_paths() -> None:
    replay_cache = {"action:nonce:session"}
    replay_non_list, replay_with_list = _paired_results(
        claims=BASE_CLAIMS,
        replay_cache=replay_cache,
    )
    _assert_post_check_parity(
        replay_non_list,
        replay_with_list,
        expected_status="invalid",
        expected_failure_type="replay_detected",
    )

    expired_non_list, expired_with_list = _paired_results(
        claims=BASE_CLAIMS,
        now_ts=2100,
    )
    _assert_post_check_parity(
        expired_non_list,
        expired_with_list,
        expected_status="stale",
        expected_failure_type="expired_token",
    )

    revoked_non_list, revoked_with_list = _paired_results(
        claims=BASE_CLAIMS,
        revocation_state="revoked_pending",
    )
    _assert_post_check_parity(
        revoked_non_list,
        revoked_with_list,
        expected_status="revoked_pending",
        expected_failure_type="revocation_pending",
    )

    partial_non_list, partial_with_list = _paired_results(
        claims=BASE_CLAIMS,
        config={
            "allow_partial_validation": True,
            "partial_validation_requires_confirmation": True,
            "partial_validation_confirmation": False,
        },
    )
    _assert_post_check_parity(
        partial_non_list,
        partial_with_list,
        expected_status="invalid",
        expected_failure_type="partial_validation_confirmation_required",
    )

    skew_exceeded_non_list, skew_exceeded_with_list = _paired_results(
        claims=BASE_CLAIMS,
        issuance_ts_local=1100,
    )
    _assert_post_check_parity(
        skew_exceeded_non_list,
        skew_exceeded_with_list,
        expected_status="invalid",
        expected_failure_type="timestamp_skew_exceeded",
    )

    skew_within_non_list, skew_within_with_list = _paired_results(
        claims=BASE_CLAIMS,
        issuance_ts_local=1010,
    )
    _assert_post_check_parity(
        skew_within_non_list,
        skew_within_with_list,
        expected_status="valid",
        expected_failure_type="timestamp_skew_within_tolerance",
    )

    valid_non_list, valid_with_list = _paired_results(claims=BASE_CLAIMS)
    _assert_post_check_parity(
        valid_non_list,
        valid_with_list,
        expected_status="valid",
        expected_failure_type=None,
    )
