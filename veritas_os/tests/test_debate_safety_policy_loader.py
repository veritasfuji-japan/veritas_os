"""Tests for Debate safety policy shadow loader and parity report."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from veritas_os.policy.debate_safety_policy_loader import (
    build_debate_safety_policy_shadow_report,
    DebateSafetyPolicySchemaError,
    DebateSafetyPolicyYamlSyntaxError,
    compare_policy_to_hardcoded_inventory,
    export_hardcoded_debate_safety_inventory,
    load_debate_safety_policy_from_yaml,
)
from veritas_os.core import debate
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
    assert report.status != "enforcement_ready"
    assert report.status != "authoritative"
    assert report.hardcoded_pattern_count is not None
    assert report.yaml_pattern_count >= 1
    assert any(
        "Runtime enforcement remains hardcoded" in note
        or "semantic parity" in note.lower()
        for note in report.notes
    )


def test_export_hardcoded_inventory_has_non_empty_categories_and_counts() -> None:
    inventory = export_hardcoded_debate_safety_inventory()

    assert inventory["source"] == debate.__name__
    assert inventory["authoritative"] is True
    assert isinstance(inventory["categories"], dict)
    assert len(inventory["categories"]) >= 1
    assert inventory["total_pattern_count"] > 0

    for category_name, metadata in inventory["categories"].items():
        assert category_name
        assert isinstance(metadata["pattern_count"], int)
        assert metadata["pattern_count"] >= 0
    assert sum(
        meta["pattern_count"] for meta in inventory["categories"].values()
    ) == inventory["total_pattern_count"]


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
    assert report["parity_status"] in {"parity_unknown", "partial_parity"}
    assert report["yaml_category_count"] >= 1
    assert report["hardcoded_category_count"] >= 1
    assert report["notes"]
    assert report["enforcement_authoritative"] == "hardcoded"

MIGRATION_MAP_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "architecture"
    / "debate-safety-policy-migration-map.yaml"
)

_ALLOWED_MIGRATION_STATUS = {"direct", "split", "merge", "derived", "TBD"}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}


def test_migration_map_yaml_covers_hardcoded_inventory_exactly() -> None:
    """Ensure planning mapping artifact fully and explicitly covers hardcoded categories."""
    payload = yaml.safe_load(MIGRATION_MAP_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    mappings = payload.get("mappings")
    assert isinstance(mappings, list)

    hardcoded_inventory = export_hardcoded_debate_safety_inventory()
    hardcoded_categories = set(hardcoded_inventory["categories"].keys())

    mapped_categories: list[str] = []
    for entry in mappings:
        assert isinstance(entry, dict)

        hardcoded_category = entry.get("hardcoded_category")
        proposed_yaml_category = entry.get("proposed_yaml_category")
        migration_status = entry.get("migration_status")

        assert isinstance(hardcoded_category, str)
        assert hardcoded_category.strip()
        assert hardcoded_category not in mapped_categories

        assert isinstance(proposed_yaml_category, str)
        assert proposed_yaml_category.strip()

        assert migration_status in _ALLOWED_MIGRATION_STATUS
        risk_level = entry.get("risk_level")
        assert risk_level in _ALLOWED_RISK_LEVELS, (
            f"Entry '{hardcoded_category}' has invalid risk_level: {risk_level!r}"
        )

        mapped_categories.append(hardcoded_category)

    mapped_categories_set = set(mapped_categories)
    missing_categories = sorted(hardcoded_categories - mapped_categories_set)
    unknown_categories = sorted(mapped_categories_set - hardcoded_categories)

    assert missing_categories == []
    assert unknown_categories == []
    assert len(mapped_categories) == len(hardcoded_categories)
