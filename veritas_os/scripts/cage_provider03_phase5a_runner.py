"""Run the VERITAS / CAGE Phase 5A loopback runtime proof.

The primary path imports the real CAGE Provider03 client from a caller-supplied,
source-pinned CAGE checkout and sends HTTP requests to the VERITAS Phase 5A
runtime surface.  It never performs an external business effect.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import importlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from veritas_os.governance.cage_provider03_phase5a_runtime import PHASE5A_PROOF_ID


FIELD_MAP = {"amount": "magnitude", "symbol": "context"}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "__dict__"):
        return {str(k): _jsonable(v) for k, v in vars(value).items()}
    return value


def _finding_codes(result: Any) -> list[str]:
    findings = getattr(result, "findings", None) or []
    codes: list[str] = []
    for finding in findings:
        if isinstance(finding, dict) and finding.get("code"):
            codes.append(str(finding["code"]))
    return codes


def _load_cage_provider(cage_repo: Path):
    if not cage_repo.is_dir():
        raise RuntimeError(f"CAGE checkout not found: {cage_repo}")
    sys.path.insert(0, str(cage_repo))
    try:
        module = importlib.import_module("src.integrations.provider_03.provider")
    finally:
        # Keep imported CAGE modules in sys.modules while avoiding accidental
        # precedence for later unrelated imports.
        try:
            sys.path.remove(str(cage_repo))
        except ValueError:
            pass
    provider_cls = getattr(module, "Provider03NormativeProvider")
    return module, provider_cls


class _SlowHandler(BaseHTTPRequestHandler):
    """Local-only slow endpoint used to exercise the CAGE timeout path."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return None

    def do_POST(self) -> None:  # noqa: N802
        time.sleep(0.25)
        body = b'{"verdict":"APPROVED","findings":[]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass


def _start_slow_server() -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


async def _run(
    *,
    provider_cls: Any,
    endpoint: str,
    token: str,
) -> dict[str, Any]:
    provider = provider_cls(
        endpoint=endpoint,
        api_key=token,
        timeout=2.0,
        action_context_field_map=FIELD_MAP,
    )

    baseline = await provider.fetch_baseline("US_FED")
    if getattr(baseline, "error", None):
        raise RuntimeError(f"baseline request failed: {baseline.error}")

    cases = [
        ("scenario_a_allowed_internal_escalation", True, "APPROVED"),
        ("scenario_d_stale_sanctions_screening", False, "ESCALATE"),
        ("scenario_b_prohibited_account_freeze", False, "REJECTED"),
    ]
    validations: list[dict[str, Any]] = []
    for scenario_name, expected_admitted, expected_verdict in cases:
        result = await provider.validate_fria(
            {
                "action": "aml_kyc_regulated_action",
                "veritas_scenario_name": scenario_name,
                "action_context": {
                    "amount": 1000,
                    "symbol": "acct",
                },
            }
        )
        admitted = bool(getattr(result, "admitted", False))
        if admitted is not expected_admitted:
            raise RuntimeError(
                f"{scenario_name}: expected admitted={expected_admitted}, got {admitted}"
            )
        if expected_verdict == "ESCALATE":
            review_markers = [
                finding
                for finding in (getattr(result, "findings", None) or [])
                if isinstance(finding, dict) and finding.get("needs_human_review") is True
            ]
            if not review_markers:
                raise RuntimeError("ESCALATE did not preserve needs_human_review=true")
        validations.append(
            {
                "scenario_name": scenario_name,
                "expected_provider03_verdict": expected_verdict,
                "cage_validation_result": _jsonable(result),
            }
        )

    evidence_hash = hashlib.sha256(b"phase5a-runtime-evidence").hexdigest()
    evidence = await provider.submit_evidence("phase5a::runtime", evidence_hash)
    if getattr(evidence, "error", None):
        raise RuntimeError(f"evidence submission failed: {evidence.error}")
    if not getattr(evidence, "seal_hash", ""):
        raise RuntimeError("evidence submission returned no seal hash")

    bad_auth_provider = provider_cls(
        endpoint=endpoint,
        api_key="phase5a-intentionally-invalid-token",
        timeout=2.0,
        action_context_field_map=FIELD_MAP,
    )
    bad_auth = await bad_auth_provider.validate_fria(
        {
            "action": "aml_kyc_regulated_action",
            "veritas_scenario_name": "scenario_a_allowed_internal_escalation",
        }
    )
    bad_auth_pass = (
        getattr(bad_auth, "admitted", True) is False
        and "ENDPOINT_ERROR" in _finding_codes(bad_auth)
    )
    if not bad_auth_pass:
        raise RuntimeError("invalid bearer token did not fail closed")

    unavailable_provider = provider_cls(
        endpoint="http://127.0.0.1:1",
        api_key=token,
        timeout=0.2,
        action_context_field_map=FIELD_MAP,
    )
    unavailable = await unavailable_provider.validate_fria(
        {
            "action": "aml_kyc_regulated_action",
            "veritas_scenario_name": "scenario_a_allowed_internal_escalation",
        }
    )
    unavailable_pass = (
        getattr(unavailable, "admitted", True) is False
        and "ENDPOINT_ERROR" in _finding_codes(unavailable)
    )
    if not unavailable_pass:
        raise RuntimeError("unavailable endpoint did not fail closed")

    slow_server, slow_thread, slow_endpoint = _start_slow_server()
    try:
        timeout_provider = provider_cls(
            endpoint=slow_endpoint,
            api_key=token,
            timeout=0.05,
            action_context_field_map=FIELD_MAP,
        )
        timeout_result = await timeout_provider.validate_fria(
            {"action": "timeout_probe", "veritas_scenario_name": "timeout_probe"}
        )
    finally:
        slow_server.shutdown()
        slow_server.server_close()
        slow_thread.join(timeout=1.0)

    timeout_pass = (
        getattr(timeout_result, "admitted", True) is False
        and "ENDPOINT_ERROR" in _finding_codes(timeout_result)
    )
    if not timeout_pass:
        raise RuntimeError("timeout did not fail closed")

    return {
        "baseline": _jsonable(baseline),
        "validations": validations,
        "evidence_submission": _jsonable(evidence),
        "negative_runtime_checks": {
            "invalid_bearer_fail_closed": bad_auth_pass,
            "endpoint_unavailable_fail_closed": unavailable_pass,
            "timeout_fail_closed": timeout_pass,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cage-repo", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--veritas-source-sha", required=True)
    parser.add_argument("--cage-source-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    module, provider_cls = _load_cage_provider(args.cage_repo.resolve())
    report_body = asyncio.run(
        _run(
            provider_cls=provider_cls,
            endpoint=args.endpoint.rstrip("/"),
            token=args.token,
        )
    )

    report = {
        "format_version": "veritas-cage-phase5a-runtime/v1",
        "proof_id": PHASE5A_PROOF_ID,
        "veritas_source_sha": args.veritas_source_sha,
        "cage_source_sha": args.cage_source_sha,
        "cage_provider03_module": str(Path(module.__file__).resolve()),
        "runtime_topology": "real CAGE Provider03 client -> loopback HTTP -> VERITAS Phase5A FastAPI",
        "real_cage_provider03_client": True,
        "loopback_http": True,
        "mocked_cage_http_client": False,
        "external_effects_executed": False,
        "production_claim": False,
        "google_endorsement_claim": False,
        **report_body,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "phase5a-runtime-report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
