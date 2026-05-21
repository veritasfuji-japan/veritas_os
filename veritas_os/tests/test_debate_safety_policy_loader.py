"""Tests for Debate safety policy shadow loader and parity report."""

from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.policy.debate_safety_policy_loader import (
    build_debate_safety_policy_shadow_report,
    DebateSafetyPolicySchemaError,
    DebateSafetyPolicyYamlSyntaxError,
    compare_policy_to_hardcoded_inventory,
    export_hardcoded_debate_safety_inventory,
    load_debate_safety_policy_from_yaml,
)
from veritas_os.policy.debate_safety_policy_schema import PolicyMode


EXAMPLE_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "debate_safety_policy.example.yaml"
)


def test_loader_loads_valid_example_yaml() -> None:
    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)
    assert policy.mode == PolicyMode.example_only
    assert len(policy.categories) >= 1


def test_loader_fails_on_invalid_yaml_syntax(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad_syntax.yaml"
    bad_yaml.write_text("categories: [\n", encoding="utf-8")

    with pytest.raises(DebateSafetyPolicyYamlSyntaxError):
        load_debate_safety_policy_from_yaml(bad_yaml)


def test_loader_fails_on_schema_invalid_yaml(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_pattern_string(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid_empty_pattern.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-pattern",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns:",
                '      - ""',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_patterns_list(tmp_path: Path) -> None:
    """patterns: [] must be rejected — list itself must be non-empty (Field min_length=1)."""
    schema_invalid = tmp_path / "schema_invalid_empty_patterns_list.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-patterns-list",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_categories(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid_empty_categories.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-categories",
                "mode: example_only",
                "categories: {}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_does_not_call_runtime_enforcement(monkeypatch) -> None:
    called = {"run_debate": False}

    def _fail_run_debate(*args, **kwargs):
        called["run_debate"] = True
        raise AssertionError("run_debate must not be called by shadow loader")

    monkeypatch.setattr("veritas_os.core.debate.run_debate", _fail_run_debate)

    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)

    assert policy.policy_id
    assert called["run_debate"] is False


def test_parity_report_is_conservative_phase2() -> None:
    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)
    report = compare_policy_to_hardcoded_inventory(policy)

    assert report.status in {"shadow_only", "parity_unknown", "partial_parity"}
    assert report.status == "parity_unknown"
    assert len(report.missing_hardcoded_categories) >= 1
    assert report.hardcoded_pattern_count is not None
    assert report.yaml_pattern_count >= 1
    assert any("Runtime enforcement remains hardcoded" in note for note in report.notes)


def test_export_hardcoded_inventory_has_non_empty_categories_and_counts() -> None:
    inventory = export_hardcoded_debate_safety_inventory()

    assert inventory["source"] == "veritas_os.core.debate"
    assert inventory["authoritative"] is True
    assert isinstance(inventory["categories"], dict)
    assert len(inventory["categories"]) >= 1
    assert inventory["total_pattern_count"] > 0

    for category_name, metadata in inventory["categories"].items():
        assert category_name
        assert isinstance(metadata["pattern_count"], int)
        assert metadata["pattern_count"] >= 0


def test_export_hardcoded_inventory_category_snapshot_names_only() -> None:
    inventory = export_hardcoded_debate_safety_inventory()
    expected_categories = {
        "actionable_intent_patterns",
        "ascii_risk_negation_by_keyword",
        "benign_context_strong_terms",
        "benign_context_weak_terms",
        "danger_patterns_en",
        "danger_terms_ja",
        "dangerous_intent_patterns",
        "instructional_cue_patterns",
        "ja_risk_negation_by_keyword",
        "refusal_context_patterns",
        "regulatory_ambiguity_negation_terms",
        "regulatory_ambiguity_patterns",
        "risk_keywords_weighted",
        "risk_negation_terms",
    }
    assert set(inventory["categories"].keys()) == expected_categories


def test_build_shadow_report_visibility_fields() -> None:
    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)
    report = build_debate_safety_policy_shadow_report(policy)

    assert report["policy_id"] == policy.policy_id
    assert report["mode"] == policy.mode.value
    assert report["schema_version"] == policy.schema_version
    assert report["parity_status"] == "parity_unknown"
    assert report["yaml_category_count"] >= 1
    assert report["hardcoded_category_count"] >= 1
    assert len(report["missing_hardcoded_categories"]) >= 1
    assert report["enforcement_authoritative"] == "hardcoded"
