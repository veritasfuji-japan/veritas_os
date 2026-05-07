#!/usr/bin/env python3
"""Run a safe one-day VERITAS PoC smoke check against a running API server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 5.0
EVIDENCE_PACKET_TYPE = "veritas_one_day_poc_evidence"
EVIDENCE_SCHEMA_VERSION = "one_day_poc_evidence.v1"


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
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--base-url", default=os.getenv("VERITAS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--evidence-json", type=Path, dest="evidence_json")
    parser.add_argument("--evidence-md", type=Path, dest="evidence_md")
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
        "non_goals": [
            "not_a_runtime_deployment_reference",
            "no_jaeger_grafana_tempo_otlp_deployment",
            "no_cryptographic_human_approval_signature",
            "no_new_trustlog_durability_guarantee",
        ],
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
        print(f"Wrote sanitized evidence JSON: {args.evidence_json}")

    if args.evidence_md:
        try:
            _write_text_file(args.evidence_md, _build_evidence_markdown(evidence))
        except OSError as exc:
            print(f"ERROR: failed to write evidence Markdown: {exc}", file=sys.stderr)
            return 3
        print(f"Wrote sanitized evidence Markdown: {args.evidence_md}")

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
