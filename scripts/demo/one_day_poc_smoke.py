#!/usr/bin/env python3
"""Run a safe one-day VERITAS PoC smoke check against a running API server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 5.0
EVIDENCE_PACKET_TYPE = "veritas_one_day_poc_evidence"
EVIDENCE_SCHEMA_VERSION = "one_day_poc_evidence.v1"
EVIDENCE_SCHEMA_PATH = "schemas/poc/one_day_poc_evidence.v1.schema.json"

EXPECTED_NON_GOALS = [
    "not_a_runtime_deployment_reference",
    "no_jaeger_grafana_tempo_otlp_deployment",
    "no_cryptographic_human_approval_signature",
    "no_new_trustlog_durability_guarantee",
]
ALLOWED_STRUCTURED_LOGGING_FORMATS = {"json", "text", "unknown", None}


def _is_repo_local_doc_path(value: Any) -> bool:
    """Return True when value is a safe repo-local docs/schemas relative path."""
    if not isinstance(value, str):
        return False
    if not value or value.strip() != value:
        return False
    if "\\" in value:
        return False
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return False
    path = PurePosixPath(value)
    if path.is_absolute():
        return False
    if any(part in ("", ".", "..") for part in path.parts):
        return False
    return bool(path.parts) and path.parts[0] in {"docs", "schemas"}


def _emit_status(message: str, *, json_output: bool, error: bool = False) -> None:
    """Emit status messages to stdout, or stderr when JSON mode/error is active."""
    stream = sys.stderr if json_output or error else sys.stdout
    print(message, file=stream)

def _append_unknown_fields_errors(
    errors: list[str],
    value: Any,
    allowed: set[str],
    path: str,
) -> None:
    """Append unknown-field errors for object values."""
    if not isinstance(value, dict):
        return
    for field in sorted(set(value) - allowed):
        errors.append(f"unknown field: {path}.{field}")


def _is_utc_timestamp(value: Any) -> bool:
    """Return True for UTC timestamps in YYYY-MM-DDTHH:MM:SSZ format."""
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def _validate_evidence_packet(payload: Any) -> list[str]:
    """Validate one-day PoC evidence packet fields using lightweight stdlib checks."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]

    required_top_level = {
        "packet_type",
        "schema_version",
        "generated_at",
        "read_only",
        "mutation_allowed",
        "checks",
        "docs",
        "non_goals",
        "warnings",
    }
    unknown_fields = sorted(set(payload) - required_top_level)
    for field in unknown_fields:
        errors.append(f"unknown top-level field: {field}")

    for field in sorted(required_top_level):
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("packet_type") != EVIDENCE_PACKET_TYPE:
        errors.append("packet_type must equal veritas_one_day_poc_evidence")
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        errors.append("schema_version must equal one_day_poc_evidence.v1")
    if not isinstance(payload.get("generated_at"), str):
        errors.append("generated_at must be a string")
    elif not _is_utc_timestamp(payload.get("generated_at")):
        errors.append("generated_at must use UTC format YYYY-MM-DDTHH:MM:SSZ")
    if payload.get("read_only") is not True:
        errors.append("read_only must be true")
    if payload.get("mutation_allowed") is not False:
        errors.append("mutation_allowed must be false")

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
        checks = {}
    _append_unknown_fields_errors(
        errors,
        checks,
        {"observability_capabilities", "governance_policy_read"},
        "checks",
    )

    observability = checks.get("observability_capabilities")
    if not isinstance(observability, dict):
        errors.append("checks.observability_capabilities must be an object")
        observability = {}
    _append_unknown_fields_errors(
        errors,
        observability,
        {"status_code", "ok", "summary"},
        "checks.observability_capabilities",
    )
    if not isinstance(observability.get("status_code"), int):
        errors.append("checks.observability_capabilities.status_code must be an integer")
    if not isinstance(observability.get("ok"), bool):
        errors.append("checks.observability_capabilities.ok must be a boolean")

    summary = observability.get("summary")
    if not isinstance(summary, dict):
        errors.append("checks.observability_capabilities.summary must be an object")
        summary = {}
    _append_unknown_fields_errors(
        errors,
        summary,
        {
            "structured_logging_format",
            "opentelemetry_importable",
            "exporter_configured",
            "governance_span_chain",
            "rbac_denial_audit_append_visibility",
        },
        "checks.observability_capabilities.summary",
    )

    summary_fields = [
        "structured_logging_format",
        "opentelemetry_importable",
        "exporter_configured",
        "governance_span_chain",
        "rbac_denial_audit_append_visibility",
    ]
    for field in summary_fields:
        if field not in summary:
            errors.append(f"missing required field: checks.observability_capabilities.summary.{field}")

    if summary.get("structured_logging_format") not in ALLOWED_STRUCTURED_LOGGING_FORMATS:
        errors.append(
            "checks.observability_capabilities.summary.structured_logging_format must be json, text, unknown, or null"
        )
    for field in summary_fields[1:]:
        value = summary.get(field)
        if value is not None and not isinstance(value, bool):
            errors.append(
                f"checks.observability_capabilities.summary.{field} must be boolean or null"
            )

    policy_read = checks.get("governance_policy_read")
    if not isinstance(policy_read, dict):
        errors.append("checks.governance_policy_read must be an object")
        policy_read = {}
    _append_unknown_fields_errors(
        errors,
        policy_read,
        {"status_code", "required"},
        "checks.governance_policy_read",
    )
    if not isinstance(policy_read.get("status_code"), int):
        errors.append("checks.governance_policy_read.status_code must be an integer")
    if not isinstance(policy_read.get("required"), bool):
        errors.append("checks.governance_policy_read.required must be a boolean")

    docs = payload.get("docs")
    if not isinstance(docs, dict):
        errors.append("docs must be an object")
        docs = {}
    _append_unknown_fields_errors(
        errors,
        docs,
        {
            "walkthrough_en",
            "walkthrough_ja",
            "trace_span_chain_en",
            "trace_span_chain_ja",
        },
        "docs",
    )
    doc_fields = [
        "walkthrough_en",
        "walkthrough_ja",
        "trace_span_chain_en",
        "trace_span_chain_ja",
    ]
    for field in doc_fields:
        value = docs.get(field)
        if not isinstance(value, str):
            errors.append(f"docs.{field} must be a string")
        elif not _is_repo_local_doc_path(value):
            errors.append(f"docs.{field} must be a repo-local path")

    non_goals = payload.get("non_goals")
    if not isinstance(non_goals, list) or not all(isinstance(item, str) for item in non_goals):
        errors.append("non_goals must be a list of strings")
    elif non_goals != EXPECTED_NON_GOALS:
        errors.append("non_goals must match the expected one-day PoC non-goals")

    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        errors.append("warnings must be a list of strings")

    return errors


def _load_and_validate_evidence_file(path: Path) -> list[str]:
    """Load and validate an evidence JSON file without exposing raw content."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"failed to read evidence file: {exc}"]

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ["evidence file is not valid JSON"]

    return _validate_evidence_packet(payload)


def _run_evidence_validation(path: Path) -> int:
    """Validate evidence JSON file and print compact result lines."""
    errors = _load_and_validate_evidence_file(path)
    if errors:
        print("INVALID one_day_poc_evidence.v1", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("VALID one_day_poc_evidence.v1")
    return 0


def _bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _http_get_json(base_url: str, path: str, api_key: str) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"
    req = request.Request(url=url, method="GET")
    req.add_header("X-API-Key", api_key)
    req.add_header("Accept", "application/json")
    try:
        with request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": body[:300]}
    except error.URLError as exc:
        return 0, {"error": str(exc.reason)}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {"raw": body[:300]}
    return status, payload


def _extract_observability_summary(payload: dict[str, Any]) -> dict[str, Any]:
    observability = payload.get("observability")
    if not isinstance(observability, dict):
        observability = {}

    structured = observability.get("structured_logging")
    if not isinstance(structured, dict):
        structured = {}

    tracing = observability.get("tracing")
    if not isinstance(tracing, dict):
        tracing = {}

    return {
        "structured_logging_format": structured.get("format"),
        "opentelemetry_importable": tracing.get("opentelemetry_importable"),
        "exporter_configured": tracing.get("exporter_configured"),
        "governance_span_chain": tracing.get("governance_span_chain"),
        "rbac_denial_audit_append_visibility": tracing.get(
            "rbac_denial_audit_append_visibility"
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VERITAS one-day PoC smoke checks")
    parser.add_argument("--print-schema-path", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--base-url", default=os.getenv("VERITAS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--evidence-json", type=Path, dest="evidence_json")
    parser.add_argument("--evidence-md", type=Path, dest="evidence_md")
    parser.add_argument("--validate-evidence", type=Path, dest="validate_evidence")
    parser.add_argument("--validate-generated-evidence", action="store_true")
    return parser


def _write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 content to the target path."""
    path.write_text(content, encoding="utf-8")


def _build_evidence_packet(
    observability: dict[str, Any],
    capabilities_status: int,
    capabilities_ok: bool,
    policy_status: int,
    warnings: list[str],
) -> dict[str, Any]:
    """Build a sanitized one-day PoC evidence packet."""
    return {
        "packet_type": EVIDENCE_PACKET_TYPE,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True,
        "mutation_allowed": False,
        "checks": {
            "observability_capabilities": {
                "status_code": capabilities_status,
                "ok": capabilities_ok,
                "summary": observability,
            },
            "governance_policy_read": {
                "status_code": policy_status,
                "required": False,
            },
        },
        "docs": {
            "walkthrough_en": "docs/en/poc/one-day-poc-walkthrough.md",
            "walkthrough_ja": "docs/ja/poc/one-day-poc-walkthrough.md",
            "trace_span_chain_en": "docs/en/operations/governance-trace-span-chain.md",
            "trace_span_chain_ja": "docs/ja/operations/governance-trace-span-chain.md",
        },
        "non_goals": EXPECTED_NON_GOALS,
        "warnings": warnings,
    }


def _build_evidence_markdown(evidence: dict[str, Any]) -> str:
    """Render a sanitized evidence packet as Markdown."""
    checks = evidence["checks"]
    observability_check = checks["observability_capabilities"]
    observability = observability_check["summary"]
    observability_result = "PASS" if observability_check["ok"] else "FAIL"
    docs = evidence["docs"]
    lines = [
        "# VERITAS One-Day PoC Evidence Packet",
        "",
        f"Generated at: {evidence['generated_at']}",
        f"Read-only: {str(evidence['read_only']).lower()}",
        f"Mutation allowed: {str(evidence['mutation_allowed']).lower()}",
        "",
        "## Summary",
        f"- Observability capabilities: {observability_result}",
        f"- Structured logging: {observability.get('structured_logging_format')}",
        f"- OpenTelemetry importable: {observability.get('opentelemetry_importable')}",
        f"- Exporter configured: {observability.get('exporter_configured')}",
        f"- Governance span chain: {observability.get('governance_span_chain')}",
        (
            "- RBAC denial audit append visibility: "
            f"{observability.get('rbac_denial_audit_append_visibility')}"
        ),
        "",
        "## Checks",
        "### Observability Capabilities",
        f"- Status: {observability_check['status_code']}",
        f"- Result: {observability_result}",
        "",
        "### Governance Policy Read",
        f"- Status: {checks['governance_policy_read']['status_code']}",
        f"- Required: {str(checks['governance_policy_read']['required']).lower()}",
        "",
        "## Evidence Links",
        f"- One-day walkthrough EN: {docs['walkthrough_en']}",
        f"- One-day walkthrough JA: {docs['walkthrough_ja']}",
        f"- Governance trace span chain EN: {docs['trace_span_chain_en']}",
        f"- Governance trace span chain JA: {docs['trace_span_chain_ja']}",
        "",
        "## Non-goals / limitations",
    ]
    lines.extend(f"- {item}" for item in evidence["non_goals"])
    lines.extend(
        [
            "",
            "## Security boundary",
            "- API key not included.",
            "- Raw exporter endpoint not included.",
            "- Raw env values not included.",
            "- Request/response raw bodies not included.",
        ]
    )
    if evidence["warnings"]:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in evidence["warnings"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.print_schema_path:
        print(EVIDENCE_SCHEMA_PATH)
        return 0

    if args.validate_evidence:
        return _run_evidence_validation(args.validate_evidence)
    if args.validate_generated_evidence and not args.evidence_json:
        print(
            "ERROR: --validate-generated-evidence requires --evidence-json PATH",
            file=sys.stderr,
        )
        return 2

    api_key = os.getenv("VERITAS_API_KEY")
    if not api_key:
        print("ERROR: missing required API credentials", file=sys.stderr)
        return 2

    allow_mutation = _bool_env("VERITAS_DEMO_ALLOW_MUTATION", default=False)
    warnings: list[str] = []
    docs = {
        "en": "docs/en/poc/one-day-poc-walkthrough.md",
        "ja": "docs/ja/poc/one-day-poc-walkthrough.md",
    }

    capabilities_status, capabilities_payload = _http_get_json(
        args.base_url,
        "/v1/observability/capabilities",
        api_key,
    )
    capabilities_ok = capabilities_status == 200

    observability = _extract_observability_summary(
        capabilities_payload if isinstance(capabilities_payload, dict) else {}
    )

    policy_status, _policy_payload = _http_get_json(
        args.base_url,
        "/v1/governance/policy",
        api_key,
    )
    if policy_status not in (200, 401, 403, 404):
        warnings.append(f"unexpected governance policy status: {policy_status}")

    if allow_mutation:
        warnings.append(
            "VERITAS_DEMO_ALLOW_MUTATION=true is set, but this smoke script remains read-only."
        )

    ok = capabilities_ok
    if not capabilities_ok:
        warnings.append(
            f"required check failed: GET /v1/observability/capabilities status={capabilities_status}"
        )

    summary = {
        "ok": ok,
        "capabilities_ok": capabilities_ok,
        "observability": observability,
        "docs": docs,
        "warnings": warnings,
    }
    evidence = _build_evidence_packet(
        observability=observability,
        capabilities_status=capabilities_status,
        capabilities_ok=capabilities_ok,
        policy_status=policy_status,
        warnings=warnings,
    )

    if args.evidence_json:
        try:
            _write_text_file(
                args.evidence_json,
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            )
        except OSError as exc:
            print(f"ERROR: failed to write evidence JSON: {exc}", file=sys.stderr)
            return 3
        _emit_status(
            f"Wrote sanitized evidence JSON: {args.evidence_json}",
            json_output=args.json_output,
        )
        if args.validate_generated_evidence:
            generated_errors = _load_and_validate_evidence_file(args.evidence_json)
            if generated_errors:
                _emit_status(
                    "Generated evidence validation: INVALID one_day_poc_evidence.v1",
                    json_output=args.json_output,
                    error=True,
                )
                for item in generated_errors:
                    print(f"- {item}", file=sys.stderr)
                return 1
            _emit_status(
                "Generated evidence validation: VALID one_day_poc_evidence.v1",
                json_output=args.json_output,
            )

    if args.evidence_md:
        try:
            _write_text_file(args.evidence_md, _build_evidence_markdown(evidence))
        except OSError as exc:
            print(f"ERROR: failed to write evidence Markdown: {exc}", file=sys.stderr)
            return 3
        _emit_status(
            f"Wrote sanitized evidence Markdown: {args.evidence_md}",
            json_output=args.json_output,
        )

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
