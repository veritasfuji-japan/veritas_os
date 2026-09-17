"""Run the VERITAS / CAGE Phase 5B verdict and fail-closed runtime matrix.

The proof uses a source-pinned real CAGE Provider03 client.  Normal verdicts are
sent over loopback HTTP to the merged VERITAS Phase 5A runtime surface.  A
second local-only fault server exercises CAGE response and transport failure
semantics without performing any external business effect.

Phase 5B deliberately records upstream CAGE exceptions as evidence rather than
wrapping them in a VERITAS shim and calling that equivalent fail-closed behavior.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import dataclasses
import importlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

PHASE5B_PROOF_ID: Final[str] = "veritas-cage-provider03-phase5b-fail-closed-v1"
FIELD_MAP: Final[dict[str, str]] = {"amount": "magnitude", "symbol": "context"}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {str(key): _jsonable(item) for key, item in vars(value).items()}
    return value


def _finding_codes(result: Any) -> list[str]:
    findings = getattr(result, "findings", None) or []
    return [
        str(finding["code"])
        for finding in findings
        if isinstance(finding, dict) and finding.get("code")
    ]


def _load_cage_provider(cage_repo: Path):
    if not cage_repo.is_dir():
        raise RuntimeError(f"CAGE checkout not found: {cage_repo}")
    sys.path.insert(0, str(cage_repo))
    try:
        module = importlib.import_module("src.integrations.provider_03.provider")
    finally:
        try:
            sys.path.remove(str(cage_repo))
        except ValueError:
            pass
    return module, getattr(module, "Provider03NormativeProvider")


def _expr_name(node: ast.expr | None) -> str:
    if node is None:
        return "bare"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expr_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Tuple):
        return "|".join(_expr_name(item) for item in node.elts)
    return type(node).__name__


def _contains_validate_fria_call(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == "validate_fria":
            return True
    return False


def _find_class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.AST:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                return child
    raise RuntimeError(f"source method not found: {class_name}.{method_name}")


def _find_function(tree: ast.Module, function_name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise RuntimeError(f"source function not found: {function_name}")


def _except_handlers(function_node: ast.AST) -> list[str]:
    handlers: set[str] = set()
    for node in ast.walk(function_node):
        if isinstance(node, ast.ExceptHandler):
            handlers.add(_expr_name(node.type))
    return sorted(handlers)


def _sync_gate_handlers(function_node: ast.AST) -> list[str]:
    handlers: set[str] = set()
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Try):
            continue
        if not any(_contains_validate_fria_call(item) for item in node.body):
            continue
        for handler in node.handlers:
            handlers.add(_expr_name(handler.type))
    return sorted(handlers)


def audit_cage_source(cage_repo: Path) -> dict[str, Any]:
    """Record the exact exception boundaries in the pinned CAGE source."""

    provider_path = cage_repo / "src/integrations/provider_03/provider.py"
    kernel_path = cage_repo / "src/gateway/governance/normative_provider.py"
    if not provider_path.is_file() or not kernel_path.is_file():
        raise RuntimeError("pinned CAGE checkout is missing Provider03 or kernel source")

    provider_tree = ast.parse(provider_path.read_text(encoding="utf-8"))
    kernel_tree = ast.parse(kernel_path.read_text(encoding="utf-8"))
    validate_node = _find_class_method(
        provider_tree,
        "Provider03NormativeProvider",
        "validate_fria",
    )
    enforce_node = _find_function(kernel_tree, "enforce_fria_boundary")

    adapter_handlers = _except_handlers(validate_node)
    sync_handlers = _sync_gate_handlers(enforce_node)
    return {
        "provider03_validate_exception_handlers": adapter_handlers,
        "provider03_validate_catches_json_decode_error": any(
            handler.endswith("JSONDecodeError") for handler in adapter_handlers
        ),
        "sync_gate_validate_exception_handlers": sync_handlers,
        "sync_gate_catches_generic_exception": any(
            handler in {"Exception", "BaseException"} for handler in sync_handlers
        ),
        "provider03_source": str(provider_path),
        "kernel_source": str(kernel_path),
    }


class _FaultMatrixHandler(BaseHTTPRequestHandler):
    """Local-only Provider03 fault endpoint for deterministic negative tests."""

    counts: dict[str, int] = {}
    counts_lock = threading.Lock()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return None

    @classmethod
    def count(cls, probe: str) -> int:
        with cls.counts_lock:
            return cls.counts.get(probe, 0)

    @classmethod
    def reset(cls) -> None:
        with cls.counts_lock:
            cls.counts = {}

    def _record(self, probe: str) -> None:
        with type(self).counts_lock:
            type(self).counts[probe] = type(self).counts.get(probe, 0) + 1

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "application/json",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        probe = str(payload.get("phase5b_probe") or "default")
        self._record(probe)

        if probe == "unknown_verdict":
            self._send_json(
                200,
                {
                    "verdict": "FUTURE_UNKNOWN",
                    "findings": [{"code": "phase5b.unknown_verdict"}],
                },
            )
            return
        if probe == "missing_verdict":
            self._send_json(
                200,
                {"findings": [{"code": "phase5b.missing_verdict"}]},
            )
            return
        if probe == "http_500":
            self._send_json(500, {"error": "phase5b.synthetic_http_500"})
            return
        if probe == "slow_response":
            time.sleep(0.25)
            self._send_json(200, {"verdict": "APPROVED", "findings": []})
            return
        if probe == "malformed_json":
            self._send_bytes(200, b'{"verdict":')
            return
        if probe == "null_verdict":
            self._send_json(200, {"verdict": None, "findings": []})
            return

        self._send_json(200, {"verdict": "APPROVED", "findings": []})


def _start_fault_server() -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    _FaultMatrixHandler.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FaultMatrixHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


def _result_failed_closed(result: Any) -> bool:
    return getattr(result, "admitted", True) is False


async def _capture_exception_or_result(awaitable: Any) -> dict[str, Any]:
    try:
        result = await awaitable
    except Exception as exc:  # evidence capture: exact upstream exception is intentional
        return {
            "returned_result": False,
            "fail_closed_result_returned": False,
            "unsafe_admit": False,
            "exception_type": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "exception_message": str(exc),
        }

    admitted = bool(getattr(result, "admitted", False))
    return {
        "returned_result": True,
        "fail_closed_result_returned": admitted is False,
        "unsafe_admit": admitted is True,
        "exception_type": None,
        "exception_module": None,
        "exception_message": None,
        "result": _jsonable(result),
    }


async def _run(
    *,
    provider_cls: Any,
    veritas_endpoint: str,
    token: str,
    cage_repo: Path,
) -> dict[str, Any]:
    normal_provider = provider_cls(
        endpoint=veritas_endpoint,
        api_key=token,
        timeout=2.0,
        action_context_field_map=FIELD_MAP,
    )

    normal_cases = [
        ("scenario_a_allowed_internal_escalation", True, "APPROVED"),
        ("scenario_d_stale_sanctions_screening", False, "ESCALATE"),
        ("scenario_b_prohibited_account_freeze", False, "REJECTED"),
    ]
    normal_results: list[dict[str, Any]] = []
    for scenario_name, expected_admitted, expected_verdict in normal_cases:
        result = await normal_provider.validate_fria(
            {
                "action": "aml_kyc_regulated_action",
                "veritas_scenario_name": scenario_name,
                "action_context": {"amount": 1000, "symbol": "acct"},
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
                raise RuntimeError("ESCALATE lost needs_human_review=true")
        normal_results.append(
            {
                "scenario_name": scenario_name,
                "expected_provider03_verdict": expected_verdict,
                "expected_admitted": expected_admitted,
                "observed": _jsonable(result),
            }
        )

    fault_server, fault_thread, fault_endpoint = _start_fault_server()
    try:
        fault_provider = provider_cls(
            endpoint=fault_endpoint,
            api_key="phase5b-local-fault-token",
            timeout=1.0,
            action_context_field_map=FIELD_MAP,
        )

        unknown = await fault_provider.validate_fria(
            {"action": "phase5b_probe", "phase5b_probe": "unknown_verdict"}
        )
        missing = await fault_provider.validate_fria(
            {"action": "phase5b_probe", "phase5b_probe": "missing_verdict"}
        )
        http_500 = await fault_provider.validate_fria(
            {"action": "phase5b_probe", "phase5b_probe": "http_500"}
        )

        timeout_provider = provider_cls(
            endpoint=fault_endpoint,
            api_key="phase5b-local-fault-token",
            timeout=0.05,
            action_context_field_map=FIELD_MAP,
        )
        timeout_result = await timeout_provider.validate_fria(
            {"action": "phase5b_probe", "phase5b_probe": "slow_response"}
        )

        dispatch_before = sum(_FaultMatrixHandler.counts.values())
        collision = await fault_provider.validate_fria(
            {
                "action": "phase5b_probe",
                "phase5b_probe": "collision_should_not_dispatch",
                "action_context": {
                    "amount": 1000,
                    "magnitude": 1000,
                },
            }
        )
        dispatch_after = sum(_FaultMatrixHandler.counts.values())

        malformed = await _capture_exception_or_result(
            fault_provider.validate_fria(
                {"action": "phase5b_probe", "phase5b_probe": "malformed_json"}
            )
        )
        null_verdict = await _capture_exception_or_result(
            fault_provider.validate_fria(
                {"action": "phase5b_probe", "phase5b_probe": "null_verdict"}
            )
        )
    finally:
        fault_server.shutdown()
        fault_server.server_close()
        fault_thread.join(timeout=1.0)

    fail_closed_matrix = {
        "unknown_verdict_fail_closed": _result_failed_closed(unknown),
        "missing_verdict_fail_closed": _result_failed_closed(missing),
        "http_500_fail_closed": (
            _result_failed_closed(http_500) and "ENDPOINT_ERROR" in _finding_codes(http_500)
        ),
        "timeout_fail_closed": (
            _result_failed_closed(timeout_result)
            and "ENDPOINT_ERROR" in _finding_codes(timeout_result)
        ),
        "mapping_collision_fail_closed": (
            _result_failed_closed(collision)
            and "MAPPING_COLLISION" in _finding_codes(collision)
        ),
        "mapping_collision_pre_dispatch": dispatch_before == dispatch_after,
    }
    if not all(fail_closed_matrix.values()):
        failed = sorted(key for key, value in fail_closed_matrix.items() if not value)
        raise RuntimeError(f"Phase 5B fail-closed matrix failure: {failed}")

    source_audit = audit_cage_source(cage_repo)
    malformed["gap_reproduced"] = (
        malformed["fail_closed_result_returned"] is False
        and malformed["unsafe_admit"] is False
        and bool(malformed["exception_type"])
    )
    null_verdict["gap_reproduced"] = (
        null_verdict["fail_closed_result_returned"] is False
        and null_verdict["unsafe_admit"] is False
        and bool(null_verdict["exception_type"])
    )

    blockers: list[str] = []
    if not malformed["fail_closed_result_returned"]:
        blockers.append("malformed_json_response_not_converted_to_ValidationResult")
    if not null_verdict["fail_closed_result_returned"]:
        blockers.append("non_string_verdict_not_converted_to_ValidationResult")

    return {
        "normal_verdict_matrix": normal_results,
        "fail_closed_matrix": fail_closed_matrix,
        "known_response_contract_gaps": {
            "malformed_json": malformed,
            "null_verdict": null_verdict,
        },
        "cage_source_audit": source_audit,
        "phase5b_status": (
            "READY_FOR_PHASE5C" if not blockers else "BLOCKED_ON_CAGE_RESPONSE_FAIL_CLOSED_CONTRACT"
        ),
        "phase5b_blockers": blockers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cage-repo", type=Path, required=True)
    parser.add_argument("--veritas-endpoint", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--veritas-source-sha", required=True)
    parser.add_argument("--cage-source-sha", required=True)
    parser.add_argument("--cage-phase4-baseline", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cage_repo = args.cage_repo.resolve()
    module, provider_cls = _load_cage_provider(cage_repo)
    report_body = asyncio.run(
        _run(
            provider_cls=provider_cls,
            veritas_endpoint=args.veritas_endpoint.rstrip("/"),
            token=args.token,
            cage_repo=cage_repo,
        )
    )

    report = {
        "format_version": "veritas-cage-phase5b-runtime/v1",
        "proof_id": PHASE5B_PROOF_ID,
        "veritas_source_sha": args.veritas_source_sha,
        "cage_source_sha": args.cage_source_sha,
        "cage_phase4_approved_baseline": args.cage_phase4_baseline,
        "cage_provider03_module": str(Path(module.__file__).resolve()),
        "runtime_topology": (
            "real CAGE Provider03 -> loopback VERITAS Phase5A runtime + local fault matrix"
        ),
        "real_cage_provider03_client": True,
        "loopback_http": True,
        "mocked_cage_http_client": False,
        "external_effects_executed": False,
        "production_claim": False,
        "google_endorsement_claim": False,
        "commercial_integration_claim": False,
        **report_body,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "phase5b-runtime-report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
