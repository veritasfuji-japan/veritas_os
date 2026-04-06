"""Unit tests for finding normalization/padding in pipeline_critique."""

from veritas_os.core.pipeline.pipeline_critique import (
    _normalize_finding_item,
    _pad_findings,
)


def test_normalize_finding_item_converts_alias_fields() -> None:
    """`issue` and raw `details` should be converted into canonical finding shape."""
    finding = _normalize_finding_item(
        {
            "severity": "high",
            "issue": "raw issue",
            "details": "text-details",
            "fix": 123,
        }
    )
    assert finding["severity"] == "high"
    assert finding["message"] == "raw issue"
    assert finding["code"] == "CRITIQUE_GENERIC"
    assert finding["details"] == {"raw": "text-details"}
    assert finding["fix"] == "123"


def test_pad_findings_keeps_schema_for_defaults_and_input_items() -> None:
    """Padding should preserve canonical fields for both input and default items."""
    findings = _pad_findings([{"message": "hello"}], min_items=3)
    assert len(findings) == 3
    for item in findings:
        assert item["severity"] in {"low", "med", "high"}
        assert isinstance(item["message"], str) and item["message"]
        assert isinstance(item["code"], str) and item["code"]
