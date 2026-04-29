"""OpenAPI contract checks for additive pre-bind decide response fields."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_openapi_spec() -> dict[str, Any]:
    with (REPO_ROOT / "openapi.yaml").open("r", encoding="utf-8") as file_obj:
        return yaml.safe_load(file_obj)


def test_decide_response_includes_additive_pre_bind_fields() -> None:
    spec = _load_openapi_spec()
    props = spec["components"]["schemas"]["DecideResponse"]["properties"]

    for key in (
        "participation_signal",
        "pre_bind_detection_summary",
        "pre_bind_detection_detail",
        "pre_bind_preservation_summary",
        "pre_bind_preservation_detail",
    ):
        assert key in props


def test_decide_response_pre_bind_fields_remain_optional_and_bind_fields_survive() -> None:
    spec = _load_openapi_spec()
    schema = spec["components"]["schemas"]["DecideResponse"]
    props = schema["properties"]

    required = set(schema.get("required", []))
    assert "pre_bind_detection_summary" not in required
    assert "pre_bind_preservation_summary" not in required

    for bind_key in (
        "bind_outcome",
        "bind_failure_reason",
        "bind_reason_code",
        "bind_receipt_id",
        "execution_intent_id",
        "bind_summary",
    ):
        assert bind_key in props


def test_pre_bind_state_enums_match_public_vocabulary() -> None:
    spec = _load_openapi_spec()
    schemas = spec["components"]["schemas"]

    detection_state_enum = schemas["PreBindDetectionSummary"]["properties"][
        "participation_state"
    ]["enum"]
    preservation_state_enum = schemas["PreBindPreservationSummary"]["properties"][
        "preservation_state"
    ]["enum"]

    assert detection_state_enum == ["informative", "participatory", "decision_shaping"]
    assert preservation_state_enum == ["open", "degrading", "collapsed"]
