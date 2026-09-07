"""Scalar dispatch preserves each boundary's JSON and rejection semantics."""

from datetime import datetime, timezone
from decimal import Decimal
from importlib import import_module

import pytest
from pydantic import BaseModel

NORMALIZERS = [
    ("human_approval_requirement_resolution", "_json"),
    ("canonical_promotion_reference_adapter_rehearsal", "_json"),
    ("canonical_promotion_adapter_dry_run_fixture_result", "_json_value"),
    ("canonical_promotion_live_adapter_dry_run_authority_evidence_linkage", "_json"),
    ("canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review", "_json"),
    (
        "canonical_promotion_live_adapter_dry_run_credential_authorization",
        "_json_value",
    ),
    ("canonical_promotion_live_adapter_dry_run_operator_dispatch_review", "_json"),
    ("canonical_promotion_live_adapter_dry_run_endpoint_allowlist", "_json_value"),
    ("canonical_promotion_live_adapter_dry_run_dispatch_readiness", "_json_value"),
    ("canonical_promotion_live_adapter_dry_run_request", "_json_value"),
    ("canonical_promotion_live_adapter_dry_run_readiness", "_json"),
]


@pytest.fixture(params=NORMALIZERS, ids=[item[0] for item in NORMALIZERS])
def normalize(request):
    module, name = request.param
    return getattr(import_module("veritas_os.policy." + module), name)


def test_nested_scalars_and_models_preserve_values_without_container_aliases(normalize):
    class Envelope(BaseModel):
        content: dict

    payload = {
        "text": "é日本語\n",
        "none": None,
        "yes": True,
        "no": False,
        "large": 2**90,
        "nested": ({"finite": -0.25}, 0, -2, ""),
    }
    expected = {**payload, "nested": [{"finite": -0.25}, 0, -2, ""]}
    actual = normalize(payload)
    assert actual == expected
    assert actual is not payload and actual["nested"][0] is not payload["nested"][0]
    assert normalize(Envelope(content=payload)) == {"content": expected}
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    assert normalize({"time": now}) == {"time": now.isoformat()}


def test_scalar_subclasses_keep_the_existing_path(normalize):
    class Text(str):
        pass

    class Integer(int):
        pass

    text, number = Text("custom"), Integer(42)
    assert normalize(text) is text and normalize(number) is number


@pytest.mark.parametrize(
    "invalid",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("1"),
        b"bytes",
        object(),
        {1: "non-string-key"},
        datetime(2026, 9, 7),
    ],
)
def test_invalid_nested_values_still_fail_closed(normalize, invalid):
    with pytest.raises(ValueError):
        normalize({"nested": [invalid]})
