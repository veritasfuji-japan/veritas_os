"""Metadata policy, token redaction and exact provider-request binding."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json

import pytest
from pydantic import SecretBytes, ValidationError

from veritas_os.policy import sandbox_credential_resolution as module

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
TOKEN = b"synthetic.only.test.token"


def request():
    return module.SandboxCredentialRequest(
        "authorization", "attempt", "sandbox:token", "TEST_PROVIDER", "1",
        "sandbox:events:register", "sandbox", "https://sandbox.example.invalid",
    )


def metadata(now=NOW, **changes):
    body = asdict(request())
    body.pop("authorization_id")
    body.pop("attempt_id")
    return module.SandboxCredentialMetadata(**{
        **body, "credential_kind": "bearer", "revoked": False,
        "valid_from": (now - timedelta(seconds=60)).isoformat(),
        "valid_until": (now + timedelta(seconds=60)).isoformat(),
        "observed_at": now.isoformat(), **changes,
    })


def clock(now=NOW, **changes):
    return replace(module.SandboxClockReading(now, 100.0, now, 0.0), **changes)


@pytest.mark.parametrize("field", [
    "credential_reference_id", "credential_provider_type", "credential_version",
    "credential_scope", "credential_environment", "audience",
])
def test_each_provider_pin_must_match_independent_request(field):
    with pytest.raises(ValueError, match="METADATA_BINDING_MISMATCH"):
        module._validate_metadata(metadata(**{field: "substituted"}), request(), clock(), clock())


@pytest.mark.parametrize("changes", [
    {"revoked": True}, {"valid_until": NOW.isoformat()},
    {"valid_from": (NOW + timedelta(microseconds=1)).isoformat()},
    {"observed_at": (NOW - timedelta(seconds=1)).isoformat()},
    {"observed_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"valid_until": "not-a-time"}, {"valid_from": "2026-09-07T12:00:00"},
])
def test_revoked_expired_stale_or_invalid_metadata_rejects(changes):
    with pytest.raises(ValueError):
        module._validate_metadata(metadata(**changes), request(), clock(), clock())


@pytest.mark.parametrize("field,value", [
    ("revoked", "false"), ("revoked", 0), ("credential_kind", "other"),
    ("credential_reference_id", None), ("observed_at", 0),
])
def test_forged_pydantic_instances_are_revalidated(field, value):
    forged = metadata().model_copy(update={field: value})
    with pytest.raises(ValidationError):
        module._validate_metadata(forged, request(), clock(), clock())


def test_missing_metadata_is_not_treated_as_verified():
    with pytest.raises(ValueError):
        module._validate_metadata(None, request(), clock(), clock())
    body = metadata().model_dump()
    body.pop("revoked")
    with pytest.raises(ValidationError):
        module.SandboxCredentialMetadata(**body)


@pytest.mark.parametrize("changes", [
    {"monotonic_seconds": 106.0}, {"monotonic_seconds": 99.0},
    {"now": NOW + timedelta(seconds=6)},
    {"now": NOW - timedelta(seconds=1), "health_checked_at": NOW - timedelta(seconds=1)},
    {"uncertainty_seconds": 1.1},
])
def test_provider_elapsed_time_and_clock_health_are_enforced(changes):
    with pytest.raises(ValueError):
        module._validate_metadata(metadata(), request(), clock(), clock(**changes))


def test_descriptor_can_precede_response_but_not_its_request():
    later = clock(NOW + timedelta(seconds=1), monotonic_seconds=101.0)
    assert module._validate_metadata(metadata(), request(), clock(), later) == metadata()


def test_uncertainty_interval_cannot_extend_past_credential_expiry():
    with pytest.raises(ValueError):
        module._validate_metadata(
            metadata(valid_until=(NOW + timedelta(seconds=1)).isoformat()),
            request(), clock(), clock(uncertainty_seconds=1.0),
        )


def test_secret_wrappers_are_redacted_and_result_cannot_be_serialized():
    response = module.SandboxProviderCredential(metadata=metadata(), material=SecretBytes(TOKEN))
    result = module.SandboxResolvedCredential(None, "a" * 64, response.material)
    assert TOKEN.decode() not in repr(response) + response.model_dump_json() + repr(result)
    assert result.material.get_secret_value() == TOKEN
    with pytest.raises(TypeError):
        json.dumps(result)
    with pytest.raises(TypeError):
        asdict(result)
    with pytest.raises(TypeError):
        result.__reduce_ex__(4)
    result.close()
    with pytest.raises(ValueError, match="CREDENTIAL_CLOSED"):
        _ = result.material
