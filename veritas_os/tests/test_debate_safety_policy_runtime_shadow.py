"""Tests for Debate safety runtime shadow diagnostics (Phase 3a)."""

from __future__ import annotations

from pathlib import Path

from veritas_os.core.pipeline.pipeline_decide_stages import stage_debate
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.policy.debate_safety_policy_runtime_shadow import (
    SHADOW_PATH_ENV_VAR,
    build_debate_safety_policy_shadow_diagnostics,
    build_debate_safety_policy_shadow_diagnostics_from_env,
)

EXAMPLE_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "debate_safety_policy.example.yaml"
)


def _make_debate_test_context() -> PipelineContext:
    """Create a minimal PipelineContext fixture for stage_debate tests."""
    return PipelineContext(
        query="q",
        user_id="u",
        body={},
        context={},
        fast_mode=False,
        is_veritas_query=False,
        explicit_options=[],
        input_alts=[],
        alternatives=[{"id": "x", "world": {"utility": 1.0}}],
        chosen={},
        evidence=[],
        web_evidence=[],
        critique={},
        debate=[],
        raw={},
        plan={},
        fuji_dict={},
        telos=0.0,
        response_extras={},
    )


def test_shadow_diagnostics_not_configured_when_path_unset() -> None:
    diag = build_debate_safety_policy_shadow_diagnostics(None)
    assert diag == {
        "enabled": False,
        "status": "not_configured",
        "enforcement_authoritative": "hardcoded",
    }


def test_shadow_diagnostics_loads_valid_yaml() -> None:
    diag = build_debate_safety_policy_shadow_diagnostics(str(EXAMPLE_YAML_PATH))
    assert diag["enabled"] is True
    assert diag["status"] == "loaded"
    assert diag["policy_id"]
    assert diag["schema_version"] == 1
    assert diag["enforcement_authoritative"] == "hardcoded"


def test_shadow_diagnostics_invalid_yaml_returns_load_error(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad_syntax.yaml"
    bad_yaml.write_text("categories: [\n", encoding="utf-8")

    diag = build_debate_safety_policy_shadow_diagnostics(str(bad_yaml))
    assert diag["enabled"] is True
    assert diag["status"] == "load_error"
    assert diag["enforcement_authoritative"] == "hardcoded"


def test_shadow_diagnostics_schema_invalid_returns_schema_error(tmp_path: Path) -> None:
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

    diag = build_debate_safety_policy_shadow_diagnostics(str(schema_invalid))
    assert diag["status"] == "schema_error"
    assert diag["enforcement_authoritative"] == "hardcoded"


def test_shadow_diagnostics_no_raw_policy_content() -> None:
    diag = build_debate_safety_policy_shadow_diagnostics(str(EXAMPLE_YAML_PATH))
    assert "categories" not in diag
    assert "notes" not in diag


def test_shadow_diagnostics_rejects_remote_urls() -> None:
    diag = build_debate_safety_policy_shadow_diagnostics("https://example.com/policy.yaml")
    assert diag["enabled"] is True
    assert diag["status"] == "load_error"
    assert diag["error_type"] == "remote_path_not_allowed"


def test_stage_debate_behavior_unchanged_with_shadow_diagnostics(monkeypatch) -> None:
    class DummyDebate:
        @staticmethod
        def run_debate(**kwargs):
            return {
                "options": [{"id": "x", "verdict": "accept", "world": {"utility": 1.0}}],
                "chosen": {"id": "x"},
                "source": "dummy",
                "raw": {"safe": True},
            }

    base_ctx = _make_debate_test_context()
    ctx_with = _make_debate_test_context()

    monkeypatch.delenv(SHADOW_PATH_ENV_VAR, raising=False)
    stage_debate(base_ctx, debate_core=DummyDebate(), _warn=lambda m: None)

    monkeypatch.setenv(SHADOW_PATH_ENV_VAR, str(EXAMPLE_YAML_PATH))
    stage_debate(ctx_with, debate_core=DummyDebate(), _warn=lambda m: None)

    assert base_ctx.chosen == ctx_with.chosen
    assert base_ctx.alternatives == ctx_with.alternatives
    assert base_ctx.debate == ctx_with.debate
    assert "debate_safety_policy_shadow" in ctx_with.response_extras


def test_shadow_diagnostics_from_env_default_off(monkeypatch) -> None:
    monkeypatch.delenv(SHADOW_PATH_ENV_VAR, raising=False)
    diag = build_debate_safety_policy_shadow_diagnostics_from_env()
    assert diag["enabled"] is False
