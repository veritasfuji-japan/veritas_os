"""Docs checks for one-day PoC sample evidence packet fixtures."""

from __future__ import annotations

import json
from pathlib import Path


SAMPLE_JSON = Path("docs/en/poc/sample-one-day-poc-evidence.json")
SAMPLE_MD_EN = Path("docs/en/poc/sample-one-day-poc-evidence.md")
SAMPLE_MD_JA = Path("docs/ja/poc/sample-one-day-poc-evidence.md")
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
    content = SAMPLE_JSON.read_text(encoding="utf-8").lower()

    for value in FORBIDDEN_STRINGS:
        assert value not in content


def test_sample_evidence_markdown_forbidden_secret_markers_absent() -> None:
    for path in (SAMPLE_MD_EN, SAMPLE_MD_JA):
        content = path.read_text(encoding="utf-8").lower()
        for value in FORBIDDEN_STRINGS:
            assert value not in content
