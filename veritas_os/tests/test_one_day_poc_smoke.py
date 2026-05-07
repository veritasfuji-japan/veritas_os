"""Tests for one-day VERITAS PoC smoke script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path("scripts/demo/one_day_poc_smoke.py")


def _run_script(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    run_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )


@pytest.fixture()
def api_server(monkeypatch: pytest.MonkeyPatch) -> Any:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    state = {"mutation_called": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/v1/observability/capabilities":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {
                    "ok": True,
                    "observability": {
                        "structured_logging": {
                            "available": True,
                            "format": "json",
                            "trace_id_supported": True,
                        },
                        "tracing": {
                            "helper_available": True,
                            "opentelemetry_importable": True,
                            "exporter_configured": False,
                            "no_op_fallback": True,
                            "governance_span_chain": True,
                            "rbac_denial_events": True,
                            "rbac_denial_audit_append_visibility": True,
                        },
                        "docs": {
                            "governance_trace_span_chain_en": (
                                "docs/en/operations/governance-trace-span-chain.md"
                            ),
                            "governance_trace_span_chain_ja": (
                                "docs/ja/operations/governance-trace-span-chain.md"
                            ),
                        },
                    },
                }
                self.wfile.write(json.dumps(payload).encode("utf-8"))
                return
            if self.path == "/v1/governance/policy":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if self.path.startswith("/v1/governance/policy/update"):
                state["mutation_called"] = True
                self.send_response(405)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield url, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_missing_api_key_fails_clearly() -> None:
    result = _run_script({"VERITAS_API_KEY": ""})

    assert result.returncode != 0
    assert "missing required API credentials" in result.stderr


def test_smoke_script_standalone_import_bootstrap_works() -> None:
    result = _run_script({}, "--print-schema-path")

    assert result.returncode == 0
    assert "schemas/poc/one_day_poc_evidence.v1.schema.json" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_uses_x_api_key_header_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("one_day_poc_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    captured_headers: dict[str, str] = {}

    class DummyResponse:
        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return b"{}"

    def _fake_urlopen(req: Any, timeout: float) -> DummyResponse:
        del timeout
        captured_headers.update(dict(req.header_items()))
        return DummyResponse()

    monkeypatch.setattr(module.request, "urlopen", _fake_urlopen)

    status, _payload = module._http_get_json(
        "http://127.0.0.1:8000",
        "/v1/observability/capabilities",
        "key-for-test",
    )

    assert status == 200
    lowered = {k.lower(): v for k, v in captured_headers.items()}
    assert lowered.get("x-api-key") == "key-for-test"
    assert "authorization" not in lowered


def test_script_does_not_print_api_key(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "super-secret-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert "super-secret-key" not in result.stdout
    assert "super-secret-key" not in result.stderr


def test_capabilities_response_is_summarized(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["capabilities_ok"] is True
    assert payload["observability"]["structured_logging_format"] == "json"
    assert payload["observability"]["opentelemetry_importable"] is True
    assert payload["observability"]["exporter_configured"] is False
    assert payload["observability"]["governance_span_chain"] is True
    assert payload["observability"]["rbac_denial_audit_append_visibility"] is True


def test_unexpected_exporter_endpoint_raw_value_is_not_printed(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert "secret-exporter" not in result.stdout


def test_fixture_does_not_expose_exporter_endpoint_field(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "exporter_endpoint" not in payload["observability"]


def test_non_200_capabilities_fails_nonzero() -> None:
    result = _run_script(
        {
            "VERITAS_API_KEY": "test-key",
            "VERITAS_BASE_URL": "http://127.0.0.1:9",
        },
        "--json",
    )

    assert result.returncode != 0


def test_default_mode_does_not_call_mutation_endpoints(api_server: Any) -> None:
    base_url, state = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert state["mutation_called"] is False


def test_evidence_json_is_created_and_sanitized(api_server: Any, tmp_path: Path) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-api-key", "VERITAS_BASE_URL": base_url},
        "--json",
        "--evidence-json",
        str(output_path),
    )

    assert result.returncode == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "one_day_poc_evidence.v1"
    assert payload["checks"]["observability_capabilities"]["summary"] == {
        "structured_logging_format": "json",
        "opentelemetry_importable": True,
        "exporter_configured": False,
        "governance_span_chain": True,
        "rbac_denial_audit_append_visibility": True,
    }
    assert "not_a_runtime_deployment_reference" in payload["non_goals"]
    assert "not_a_production_deployment_reference" not in payload["non_goals"]
    serialized = output_path.read_text(encoding="utf-8")
    assert "test-api-key" not in serialized
    assert "secret-exporter" not in serialized
    assert "not_a_production_deployment_reference" not in serialized
    assert "token" not in serialized.lower()
    assert "exporter_endpoint" not in serialized


def test_evidence_markdown_is_created_and_sanitized(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "evidence.md"
    result = _run_script(
        {"VERITAS_API_KEY": "another-secret-key", "VERITAS_BASE_URL": base_url},
        "--evidence-md",
        str(output_path),
    )

    assert result.returncode == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# VERITAS One-Day PoC Evidence Packet" in content
    assert "another-secret-key" not in content
    assert "secret-exporter" not in content
    assert "token" not in content.lower()


def test_missing_api_key_does_not_create_evidence_file(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": ""},
        "--evidence-json",
        str(output_path),
    )
    assert result.returncode != 0
    assert not output_path.exists()


def test_evidence_write_failure_exits_nonzero(api_server: Any, tmp_path: Path) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "missing" / "dir" / "evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--evidence-json",
        str(output_path),
    )
    assert result.returncode != 0
    assert not output_path.exists()


def test_print_schema_path_succeeds_without_api_key() -> None:
    result = _run_script({"VERITAS_API_KEY": ""}, "--print-schema-path")

    assert result.returncode == 0
    assert result.stdout.strip() == "schemas/poc/one_day_poc_evidence.v1.schema.json"


def test_print_schema_path_no_network_and_no_evidence_files(tmp_path: Path) -> None:
    evidence_json_path = tmp_path / "should_not_exist.json"
    evidence_md_path = tmp_path / "should_not_exist.md"
    result = _run_script(
        {
            "VERITAS_API_KEY": "",
            "VERITAS_BASE_URL": "http://127.0.0.1:9",
        },
        "--print-schema-path",
        "--evidence-json",
        str(evidence_json_path),
        "--evidence-md",
        str(evidence_md_path),
        "--json",
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "schemas/poc/one_day_poc_evidence.v1.schema.json"
    assert not evidence_json_path.exists()
    assert not evidence_md_path.exists()
    assert "api_key" not in result.stdout.lower()
    assert "token" not in result.stdout.lower()
    assert "secret" not in result.stdout.lower()



def _sample_evidence_payload() -> dict[str, Any]:
    return json.loads(
        Path("docs/en/poc/sample-one-day-poc-evidence.json").read_text(encoding="utf-8")
    )


def test_validate_evidence_sample_passes_without_api_key() -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--validate-evidence",
        "docs/en/poc/sample-one-day-poc-evidence.json",
    )

    assert result.returncode == 0
    assert "VALID one_day_poc_evidence.v1" in result.stdout


def test_validate_evidence_invalid_json_fails(tmp_path: Path) -> None:
    evidence_path = tmp_path / "invalid.json"
    evidence_path.write_text("{invalid", encoding="utf-8")
    result = _run_script(
        {"VERITAS_API_KEY": ""},
        "--validate-evidence",
        str(evidence_path),
    )

    assert result.returncode != 0
    assert "INVALID one_day_poc_evidence.v1" in result.stderr


def test_validate_evidence_missing_required_field_fails(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    del payload["checks"]
    evidence_path = tmp_path / "missing_checks.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "missing required field: checks" in result.stderr


def test_validate_evidence_unknown_top_level_field_fails(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["unknown_field"] = True
    evidence_path = tmp_path / "unknown_field.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "unknown top-level field: unknown_field" in result.stderr


def test_validate_evidence_wrong_packet_type_fails(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["packet_type"] = "wrong"
    evidence_path = tmp_path / "wrong_packet_type.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "packet_type must equal veritas_one_day_poc_evidence" in result.stderr


def test_validate_evidence_rejects_external_docs_url(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["docs"]["walkthrough_en"] = "https://example.com/walkthrough"
    evidence_path = tmp_path / "external_docs_url.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "docs.walkthrough_en must be a repo-local path" in result.stderr


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "https://example.com/x",
        "http://example.com/x",
        "file:///tmp/x",
        "/etc/passwd",
        "../secret.md",
        "docs/en/../private.md",
        "docs/en/poc.md?x=1",
        "docs/en/poc.md#section",
        "docs/en/poc.md;param",
        "docs\\en\\poc.md",
        "",
        " docs/en/poc/one-day-poc-walkthrough.md",
    ],
)
def test_validate_evidence_rejects_unsafe_repo_local_doc_paths(
    tmp_path: Path, unsafe_value: str
) -> None:
    payload = _sample_evidence_payload()
    payload["docs"]["walkthrough_en"] = unsafe_value
    evidence_path = tmp_path / "unsafe_docs_path.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "docs.walkthrough_en must be a repo-local path" in result.stderr


def test_repo_local_doc_path_accepts_expected_docs_and_schema_prefixes() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("one_day_poc_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._is_repo_local_doc_path("docs/en/poc/one-day-poc-walkthrough.md")
    assert module._is_repo_local_doc_path("schemas/poc/one_day_poc_evidence.v1.schema.json")


def test_validate_evidence_does_not_create_evidence_outputs(tmp_path: Path) -> None:
    evidence_json_path = tmp_path / "should_not_create.json"
    evidence_md_path = tmp_path / "should_not_create.md"
    result = _run_script(
        {"VERITAS_API_KEY": ""},
        "--validate-evidence",
        "docs/en/poc/sample-one-day-poc-evidence.json",
        "--evidence-json",
        str(evidence_json_path),
        "--evidence-md",
        str(evidence_md_path),
    )

    assert result.returncode == 0
    assert not evidence_json_path.exists()
    assert not evidence_md_path.exists()

def test_validate_evidence_rejects_unknown_nested_fields(tmp_path: Path) -> None:
    cases = [
        ("checks", "unknown field: checks.extra"),
        (
            "checks.observability_capabilities",
            "unknown field: checks.observability_capabilities.extra",
        ),
        (
            "checks.observability_capabilities.summary",
            "unknown field: checks.observability_capabilities.summary.extra",
        ),
        (
            "checks.governance_policy_read",
            "unknown field: checks.governance_policy_read.extra",
        ),
        ("docs", "unknown field: docs.extra"),
    ]
    for path_name, expected_error in cases:
        payload = _sample_evidence_payload()
        target = payload
        for key in path_name.split("."):
            target = target[key]
        target["extra"] = True
        evidence_path = tmp_path / f"{path_name.replace('.', '_')}.json"
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")

        result = _run_script(
            {"VERITAS_API_KEY": ""},
            "--validate-evidence",
            str(evidence_path),
        )

        assert result.returncode != 0
        assert expected_error in result.stderr


def test_validate_evidence_generated_at_must_be_utc_format(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["generated_at"] = "not-a-date"
    evidence_path = tmp_path / "bad_generated_at.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "generated_at must use UTC format YYYY-MM-DDTHH:MM:SSZ" in result.stderr


def test_validate_evidence_generated_at_utc_sample_is_valid(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["generated_at"] = "2026-01-01T00:00:00Z"
    evidence_path = tmp_path / "valid_generated_at.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode == 0
    assert "VALID one_day_poc_evidence.v1" in result.stdout


def test_validate_evidence_generated_at_plus_offset_is_invalid(tmp_path: Path) -> None:
    payload = _sample_evidence_payload()
    payload["generated_at"] = "2026-01-01T00:00:00+00:00"
    evidence_path = tmp_path / "invalid_generated_at_offset.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "generated_at must use UTC format YYYY-MM-DDTHH:MM:SSZ" in result.stderr


def test_validate_evidence_generated_at_fractional_seconds_is_invalid(
    tmp_path: Path,
) -> None:
    payload = _sample_evidence_payload()
    payload["generated_at"] = "2026-01-01T00:00:00.000Z"
    evidence_path = tmp_path / "invalid_generated_at_fractional.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = _run_script({"VERITAS_API_KEY": ""}, "--validate-evidence", str(evidence_path))

    assert result.returncode != 0
    assert "generated_at must use UTC format YYYY-MM-DDTHH:MM:SSZ" in result.stderr


def test_load_and_validate_evidence_file_reads_actual_file(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("one_day_poc_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    payload = _sample_evidence_payload()
    evidence_path = tmp_path / "module_validation.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    errors = module._load_and_validate_evidence_file(evidence_path)
    assert errors == []

    payload["checks"]["extra"] = True
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    errors = module._load_and_validate_evidence_file(evidence_path)
    assert "unknown field: checks.extra" in errors


def test_validate_evidence_output_masks_secret_values(tmp_path: Path) -> None:
    evidence_path = tmp_path / "invalid_with_secret.json"
    evidence_path.write_text("not-json", encoding="utf-8")
    result = _run_script(
        {"VERITAS_API_KEY": "super-secret-key", "VERITAS_TOKEN": "token-value"},
        "--validate-evidence",
        str(evidence_path),
    )

    assert result.returncode != 0
    assert "super-secret-key" not in result.stdout
    assert "super-secret-key" not in result.stderr
    assert "token-value" not in result.stdout
    assert "token-value" not in result.stderr


def test_print_schema_path_precedence_over_validate_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "invalid.json"
    evidence_path.write_text("{invalid", encoding="utf-8")
    result = _run_script(
        {"VERITAS_API_KEY": ""},
        "--print-schema-path",
        "--validate-evidence",
        str(evidence_path),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "schemas/poc/one_day_poc_evidence.v1.schema.json"


def test_validate_generated_evidence_succeeds_and_creates_file(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "generated_evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--evidence-json",
        str(output_path),
        "--validate-generated-evidence",
    )

    assert result.returncode == 0
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" in result.stdout
    assert output_path.exists()


def test_json_output_routes_status_lines_to_stderr(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_json = tmp_path / "generated_evidence.json"
    output_md = tmp_path / "generated_evidence.md"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
        "--evidence-json",
        str(output_json),
        "--evidence-md",
        str(output_md),
        "--validate-generated-evidence",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "Wrote sanitized evidence JSON" not in result.stdout
    assert "Generated evidence validation" not in result.stdout
    assert "Wrote sanitized evidence Markdown" not in result.stdout
    assert "Wrote sanitized evidence JSON" in result.stderr
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" in result.stderr
    assert "Wrote sanitized evidence Markdown" in result.stderr


def test_non_json_output_keeps_status_lines_on_stdout(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_json = tmp_path / "generated_evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--evidence-json",
        str(output_json),
        "--validate-generated-evidence",
    )

    assert result.returncode == 0
    assert "Wrote sanitized evidence JSON" in result.stdout
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" in result.stdout


def test_validate_generated_evidence_output_revalidates_offline(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "generated_evidence.json"
    generate_result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--evidence-json",
        str(output_path),
        "--validate-generated-evidence",
    )
    validate_result = _run_script(
        {"VERITAS_API_KEY": "", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--validate-evidence",
        str(output_path),
    )

    assert generate_result.returncode == 0
    assert validate_result.returncode == 0
    assert "VALID one_day_poc_evidence.v1" in validate_result.stdout


def test_validate_generated_evidence_requires_evidence_json() -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--validate-generated-evidence",
    )

    assert result.returncode != 0
    assert "ERROR: --validate-generated-evidence requires --evidence-json PATH" in result.stderr


def test_validate_generated_evidence_requires_evidence_json_no_network() -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--validate-generated-evidence",
    )

    assert result.returncode != 0
    assert "required check failed" not in result.stdout
    assert "urlopen error" not in result.stdout
    assert "urlopen error" not in result.stderr


def test_print_schema_path_precedence_over_validate_generated_evidence() -> None:
    result = _run_script(
        {"VERITAS_API_KEY": "", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--print-schema-path",
        "--validate-generated-evidence",
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "schemas/poc/one_day_poc_evidence.v1.schema.json"


def test_validate_evidence_precedence_over_validate_generated_evidence(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "invalid.json"
    evidence_path.write_text("{invalid", encoding="utf-8")
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": "http://127.0.0.1:9"},
        "--validate-evidence",
        str(evidence_path),
        "--validate-generated-evidence",
    )

    assert result.returncode != 0
    assert "INVALID one_day_poc_evidence.v1" in result.stderr
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" not in result.stdout


def test_validate_generated_evidence_write_failure_no_success_line(
    api_server: Any, tmp_path: Path
) -> None:
    base_url, _ = api_server
    output_path = tmp_path / "missing" / "dir" / "evidence.json"
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--evidence-json",
        str(output_path),
        "--validate-generated-evidence",
    )

    assert result.returncode != 0
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" not in result.stdout


def test_normal_run_without_validate_generated_evidence_unchanged(api_server: Any) -> None:
    base_url, _ = api_server
    result = _run_script(
        {"VERITAS_API_KEY": "test-key", "VERITAS_BASE_URL": base_url},
        "--json",
    )

    assert result.returncode == 0
    assert "Generated evidence validation: VALID one_day_poc_evidence.v1" not in result.stdout


def test_shared_helper_import_and_contract() -> None:
    from scripts.demo import one_day_poc_shared

    summary = one_day_poc_shared.extract_observability_summary({"observability": {}})
    assert isinstance(summary, dict)

    packet = one_day_poc_shared.build_evidence_packet(
        observability=summary,
        capabilities_status=200,
        capabilities_ok=True,
        policy_status=200,
        warnings=[],
    )
    assert packet["schema_version"] == "one_day_poc_evidence.v1"
    assert packet["packet_type"] == "veritas_one_day_poc_evidence"


def test_shared_evidence_packet_non_goals_is_defensive_copy() -> None:
    from scripts.demo import one_day_poc_shared

    packet = one_day_poc_shared.build_evidence_packet(
        observability={},
        capabilities_status=200,
        capabilities_ok=True,
        policy_status=403,
        warnings=[],
    )
    original = list(one_day_poc_shared.EXPECTED_NON_GOALS)
    assert isinstance(packet["non_goals"], list)

    packet["non_goals"].append("mutated")

    assert list(one_day_poc_shared.EXPECTED_NON_GOALS) == original
    assert "mutated" not in one_day_poc_shared.EXPECTED_NON_GOALS


def test_smoke_wrapper_build_evidence_packet_compatibility() -> None:
    from scripts.demo import one_day_poc_shared
    from scripts.demo import one_day_poc_smoke

    shared_packet = one_day_poc_shared.build_evidence_packet(
        observability={"structured_logging_format": "json"},
        capabilities_status=200,
        capabilities_ok=True,
        policy_status=403,
        warnings=["w"],
    )
    wrapper_packet = one_day_poc_smoke._build_evidence_packet(
        observability={"structured_logging_format": "json"},
        capabilities_status=200,
        capabilities_ok=True,
        policy_status=403,
        warnings=["w"],
    )

    assert set(wrapper_packet.keys()) == set(shared_packet.keys())
    assert wrapper_packet["schema_version"] == shared_packet["schema_version"]
    assert wrapper_packet["packet_type"] == shared_packet["packet_type"]
    assert wrapper_packet["docs"] == shared_packet["docs"]
    assert wrapper_packet["non_goals"] == shared_packet["non_goals"]
