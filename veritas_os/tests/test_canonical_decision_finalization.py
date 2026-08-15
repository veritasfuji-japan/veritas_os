"""Canonical decision pipeline-finalization boundary tests."""

from __future__ import annotations

import json
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import create_model

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.pipeline import canonical_decision_finalization as finalization
from veritas_os.governance import canonical_decision_artifact as cda_runtime

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1"
    / "vector-01.json"
)
DECISION_TS = datetime(2031, 2, 3, 4, 5, 6, 123456, tzinfo=timezone.utc)


def _payload() -> dict[str, Any]:
    vector = json.loads(VECTOR.read_text())
    return DecideResponse.model_validate(vector["source_projection"]).model_dump(
        mode="json"
    )


def _assert_reason(
    exc: pytest.ExceptionInfo[finalization.CanonicalDecisionFinalizationError],
    reason: finalization.CanonicalDecisionFinalizationReason,
) -> None:
    assert exc.value.reason_code is reason
    assert str(exc.value) == reason.value


def test_finalization_bridges_reloaded_response_class(monkeypatch) -> None:
    """The builder receives its own exact class after API class separation."""
    reloaded_response = create_model(
        "ReloadedDecideResponse",
        __base__=DecideResponse,
    )
    assert reloaded_response is not cda_runtime.DecideResponse
    monkeypatch.setattr(finalization.api_schemas, "DecideResponse", reloaded_response)
    original_builder = cda_runtime.build_canonical_decision_artifact
    observed: list[bool] = []

    def strict_builder(source, *, decision_ts):
        observed.append(type(source) is cda_runtime.DecideResponse)
        return original_builder(source, decision_ts=decision_ts)

    monkeypatch.setattr(
        cda_runtime,
        "build_canonical_decision_artifact",
        strict_builder,
    )

    artifact = finalization.finalize_canonical_decision_artifact(
        _payload(),
        decision_ts=DECISION_TS,
    )

    assert observed == [True]
    assert artifact.request_id == "req-cda-synthetic-001"


def test_request_id_is_refused_before_model_validation(monkeypatch) -> None:
    payload = _payload()
    payload["request_id"] = ""
    validation_calls = 0

    class ForbiddenResponse:
        @classmethod
        def model_validate(cls, value):
            del cls, value
            nonlocal validation_calls
            validation_calls += 1
            raise AssertionError("model validation must not run")

    monkeypatch.setattr(
        finalization.api_schemas,
        "DecideResponse",
        ForbiddenResponse,
    )

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            payload,
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.SOURCE_REQUEST_ID_MISSING,
    )
    assert validation_calls == 0


def test_null_canonical_fields_are_removed_before_stage_8() -> None:
    """Optional response nulls must not cross the persistence boundary."""
    payload = _payload()
    payload["canonical_decision_artifact"] = None
    payload["canonical_decision_trust_receipt"] = None

    finalization.finalize_canonical_decision_artifact(
        payload,
        decision_ts=DECISION_TS,
    )
    finalization.require_stage_8_payload_without_canonical_artifact(payload)

    assert "canonical_decision_artifact" not in payload
    assert "canonical_decision_trust_receipt" not in payload


def test_non_null_trust_receipt_is_refused_before_stage_8() -> None:
    """A preexisting receipt cannot be silently accepted or overwritten."""
    payload = _payload()
    payload["canonical_decision_trust_receipt"] = {"unexpected": "receipt"}

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            payload,
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.PREEXISTING_TRUST_RECEIPT_REFUSED,
    )


@pytest.mark.parametrize(
    "field",
    ["canonical_decision_artifact", "canonical_decision_trust_receipt"],
)
def test_stage_8_guard_rejects_canonical_keys_even_when_null(field: str) -> None:
    """The explicit Stage 8 guard rejects presence, not merely non-null data."""
    payload = _payload()
    payload.pop("canonical_decision_artifact", None)
    payload.pop("canonical_decision_trust_receipt", None)
    payload[field] = None

    with pytest.raises(finalization.CanonicalDecisionFinalizationError):
        finalization.require_stage_8_payload_without_canonical_artifact(payload)


def test_null_preexisting_artifact_is_removed_before_finalization() -> None:
    payload = _payload()
    assert payload["canonical_decision_artifact"] is None

    artifact = finalization.finalize_canonical_decision_artifact(
        payload,
        decision_ts=DECISION_TS,
    )

    assert "canonical_decision_artifact" not in payload
    assert artifact.decision_ts == "2031-02-03T04:05:06.123456Z"


def test_finalization_helper_has_no_clock_lookup() -> None:
    source = inspect.getsource(finalization.finalize_canonical_decision_artifact)

    assert "utc_now" not in source
    assert "datetime.now" not in source


def test_non_null_preexisting_artifact_is_refused() -> None:
    payload = _payload()
    payload["canonical_decision_artifact"] = {"decision_id": "untrusted"}

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            payload,
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.PREEXISTING_CANONICAL_ARTIFACT_REFUSED,
    )


def test_build_failure_has_stable_reason(monkeypatch) -> None:
    def fail_build(source, *, decision_ts):
        del source, decision_ts
        raise cda_runtime.CanonicalDecisionArtifactBuildError(
            cda_runtime.CanonicalDecisionArtifactBuildReason.NON_CANONICAL_JSON_VALUE
        )

    monkeypatch.setattr(
        cda_runtime,
        "build_canonical_decision_artifact",
        fail_build,
    )

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            _payload(),
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.ARTIFACT_BUILD_FAILED,
    )


def test_verification_failure_has_stable_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        cda_runtime,
        "verify_canonical_decision_artifact",
        lambda artifact: cda_runtime.CanonicalDecisionArtifactVerificationResult(
            is_valid=False,
            reason_codes=("ARTIFACT_HASH_MISMATCH",),
            artifact=artifact,
            computed_decision_hash=None,
            expected_decision_id=None,
        ),
    )

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            _payload(),
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.ARTIFACT_VERIFICATION_FAILED,
    )


def test_api_normalized_request_id_mismatch_is_refused(monkeypatch) -> None:
    original_response = finalization.api_schemas.DecideResponse

    class MismatchedResponse:
        @classmethod
        def model_validate(cls, value):
            del cls
            source = original_response.model_validate(value)
            return source.model_copy(update={"request_id": "req-mismatch"})

    monkeypatch.setattr(
        finalization.api_schemas,
        "DecideResponse",
        MismatchedResponse,
    )

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            _payload(),
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH,
    )


def test_artifact_request_id_mismatch_is_refused(monkeypatch) -> None:
    original_builder = cda_runtime.build_canonical_decision_artifact

    def mismatched_builder(source, *, decision_ts):
        artifact = original_builder(source, decision_ts=decision_ts)
        return artifact.model_copy(update={"request_id": "req-mismatch"})

    monkeypatch.setattr(
        cda_runtime,
        "build_canonical_decision_artifact",
        mismatched_builder,
    )

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.finalize_canonical_decision_artifact(
            _payload(),
            decision_ts=DECISION_TS,
        )

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.REQUEST_ID_MISMATCH,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", {"debug": "changed"}),
        ("meta", {"latency": 42}),
        ("deterministic_replay", {"snapshot": "changed"}),
        ("trust_log", {"entry": "changed"}),
        ("extras", {"metrics": {"pipeline_total_ms": 42}}),
        ("user_summary", "changed presentation"),
    ],
)
def test_excluded_field_drift_preserves_original_artifact(field, value) -> None:
    payload = _payload()
    artifact = finalization.finalize_canonical_decision_artifact(
        payload,
        decision_ts=DECISION_TS,
    )
    original = artifact.model_dump(mode="json")
    payload[field] = value

    finalization.verify_canonical_decision_source_unchanged(payload, artifact)
    finalization.attach_canonical_decision_artifact(payload, artifact)

    assert payload["canonical_decision_artifact"] == original


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["chosen"].update(title="changed choice"),
        lambda value: value["required_evidence"].append("new_evidence"),
        lambda value: value["governance_identity"].update(policy_version="v8"),
        lambda value: value.update(
            decision_status="block",
            gate_decision="block",
            business_decision="DENY",
            actionability_status="blocked",
            requires_bind_before_execution=False,
        ),
    ],
)
def test_included_field_drift_is_refused(mutation) -> None:
    payload = _payload()
    artifact = finalization.finalize_canonical_decision_artifact(
        payload,
        decision_ts=DECISION_TS,
    )
    mutation(payload)

    with pytest.raises(finalization.CanonicalDecisionFinalizationError) as exc:
        finalization.verify_canonical_decision_source_unchanged(payload, artifact)

    _assert_reason(
        exc,
        finalization.CanonicalDecisionFinalizationReason.DECISION_SOURCE_DRIFT,
    )
    assert "canonical_decision_artifact" not in payload


def test_response_model_preserves_attached_artifact() -> None:
    payload = _payload()
    artifact = finalization.finalize_canonical_decision_artifact(
        payload,
        decision_ts=DECISION_TS,
    )
    finalization.verify_canonical_decision_source_unchanged(payload, artifact)
    finalization.attach_canonical_decision_artifact(payload, artifact)

    round_trip = DecideResponse.model_validate(payload).model_dump(mode="json")

    assert round_trip["canonical_decision_artifact"] == artifact.model_dump(
        mode="json"
    )
    assert "decision_hash" not in round_trip
    assert "decision_ts" not in round_trip
    assert "verified" not in round_trip["canonical_decision_artifact"]
