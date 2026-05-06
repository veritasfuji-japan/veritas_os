#!/usr/bin/env python3
"""Run a safe one-day VERITAS PoC smoke check against a running API server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib import error, request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 5.0


def _bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _http_get_json(base_url: str, path: str, api_key: str) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"
    req = request.Request(url=url, method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
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
    return {
        "structured_logging_format": payload.get("structured_logging_format"),
        "opentelemetry_importable": payload.get("opentelemetry_importable"),
        "exporter_configured": payload.get("exporter_configured"),
        "governance_span_chain": payload.get("governance_span_chain"),
        "rbac_denial_audit_append_visibility": payload.get(
            "rbac_denial_audit_append_visibility"
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VERITAS one-day PoC smoke checks")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--base-url", default=os.getenv("VERITAS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key-env", default="VERITAS_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        print(
            f"ERROR: missing required environment variable {args.api_key_env}",
            file=sys.stderr,
        )
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

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
