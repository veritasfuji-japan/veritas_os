"""Docs checks for one-day PoC sample evidence packet fixtures."""

from __future__ import annotations

import json
from pathlib import Path


SAMPLE_JSON = Path("docs/en/poc/sample-one-day-poc-evidence.json")
SAMPLE_MD_EN = Path("docs/en/poc/sample-one-day-poc-evidence.md")
SAMPLE_MD_JA = Path("docs/ja/poc/sample-one-day-poc-evidence.md")


SCHEMA_JSON = Path("schemas/poc/one_day_poc_evidence.v1.schema.json")
EXPECTED_NON_GOALS = [
    "not_a_runtime_deployment_reference",
    "no_jaeger_grafana_tempo_otlp_deployment",
    "no_cryptographic_human_approval_signature",
    "no_new_trustlog_durability_guarantee",
]


def _assert_required_fields(payload: dict[str, object], required: list[str]) -> None:
    for field in required:
        assert field in payload


def _assert_no_unknown_fields(payload: dict[str, object], allowed: set[str]) -> None:
    assert set(payload) == allowed

FORBIDDEN_STRINGS = (
    "authorization",
    "x-api-key",
    "api_key",
    "api-key",
    "x_api_key",
    "token",
    "access_token",
    "refresh_token",
    "bearer",
    "secret",
    "client_secret",
    "private_key",
    "password",
    "passwd",
    "cookie",
    "session",
    "credential",
    "credentials",
    "http://secret",
    "collector.internal",
    "localhost",
    "127.0.0.1",
    "real-customer",
    "customer.internal",
    "production",
    "prod-",
    "live-",
    "aws_secret_access_key",
    "aws_access_key_id",
    "openai_api_key",
    "slack_bot_token",
    "github_token",
)


def test_sample_evidence_json_has_expected_schema_fields() -> None:
    payload = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))

    assert payload["packet_type"] == "veritas_one_day_poc_evidence"
    assert payload["schema_version"] == "one_day_poc_evidence.v1"
    assert payload["generated_at"] == "2026-01-01T00:00:00Z"
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert payload["checks"]["observability_capabilities"]["status_code"] == 200
    assert payload["checks"]["observability_capabilities"]["ok"] is True
    assert payload["checks"]["governance_policy_read"]["status_code"] == 200


def test_sample_evidence_json_forbidden_secret_markers_absent() -> None:
    path = SAMPLE_JSON
    content = path.read_text(encoding="utf-8").lower()

    for value in FORBIDDEN_STRINGS:
        assert value not in content, f"forbidden marker {value!r} found in {path}"


def test_sample_evidence_markdown_forbidden_secret_markers_absent() -> None:
    for path in (SAMPLE_MD_EN, SAMPLE_MD_JA):
        content = path.read_text(encoding="utf-8").lower()
        for value in FORBIDDEN_STRINGS:
            assert value not in content, f"forbidden marker {value!r} found in {path}"


def test_one_day_poc_schema_json_parses_and_expected_consts() -> None:
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))

    assert schema["title"] == "VERITAS One-Day PoC Evidence Packet"
    assert schema["properties"]["packet_type"]["const"] == "veritas_one_day_poc_evidence"
    assert schema["properties"]["schema_version"]["const"] == "one_day_poc_evidence.v1"


def test_sample_evidence_json_matches_schema_key_requirements() -> None:
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    payload = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))

    required = schema["required"]
    assert isinstance(required, list)
    _assert_required_fields(payload, required)
    _assert_no_unknown_fields(payload, set(required))

    assert payload["packet_type"] == schema["properties"]["packet_type"]["const"]
    assert payload["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert payload["read_only"] is schema["properties"]["read_only"]["const"]
    assert payload["mutation_allowed"] is schema["properties"]["mutation_allowed"]["const"]
    assert payload["non_goals"] == EXPECTED_NON_GOALS


def test_generated_evidence_json_core_contract_matches_sample_non_goals(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    from veritas_os.tests.test_one_day_poc_smoke import SCRIPT_PATH

    out = tmp_path / "generated-evidence.json"
    run_env = os.environ.copy()
    run_env.update(
        {
            "VERITAS_API_KEY": "dummy-key",
            "VERITAS_BASE_URL": "http://127.0.0.1:9",
        }
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--json",
            "--evidence-json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["packet_type"] == "veritas_one_day_poc_evidence"
    assert payload["schema_version"] == "one_day_poc_evidence.v1"
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert payload["non_goals"] == EXPECTED_NON_GOALS
