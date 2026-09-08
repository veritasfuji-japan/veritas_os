"""Committed synthetic observation sample cannot assert confirmed success."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from veritas_os.policy.sandbox_bind_execution import SandboxDispatchObservation


def sample():
    return json.loads(
        (Path(__file__).parent / "fixtures" / "sandbox_dispatch_observation.json").read_text(),
    )


def test_committed_dispatch_observation_roundtrips_without_field_loss():
    body = sample()
    assert SandboxDispatchObservation.model_validate(body).model_dump(mode="json") == body


@pytest.mark.parametrize("field,value", [
    ("state", "CONFIRMED_EFFECT"), ("state", "SUCCESS"),
    ("reason_code", "HTTP_200_PROVES_EFFECT"), ("token", "synthetic-secret"),
])
def test_observation_rejects_success_claims_and_secret_fields(field, value):
    with pytest.raises(ValidationError):
        SandboxDispatchObservation.model_validate({**sample(), field: value})
