#!/usr/bin/env python3
"""Export and check the frozen V1 executable effect-boundary inventory."""

from __future__ import annotations

import ast
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from veritas_os.policy.bind_coverage_registry import (
    load_bind_coverage_registry,
    validate_bind_coverage_registry,
)
from veritas_os.policy.bind_execution_capability import PROOF_SCOPE

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "bind-coverage-bypass-resistance-v1"
POLICY_ROOT = ROOT / "veritas_os" / "policy"
DECLARED_EFFECT_SINKS = {
    ("veritas_os/policy/bundle.py", "archive_path.open"): "local_file_io",
    ("veritas_os/policy/bundle.py", "open"): "local_file_io",
    ("veritas_os/policy/bundle.py", "tarfile.open"): "local_file_io",
    (
        "veritas_os/policy/sandbox_event_service.py",
        "app.post",
    ): "route_registration_not_dispatch",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "asyncio.open_connection",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "writer.write",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "asyncio.open_connection",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "writer.write",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "opener.open",
    ): "registered_webhook_action_or_compensation",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "transport.request",
    ): "registered_webhook_dispatch_to_exact_sink",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "self._delegate.request",
    ): "controlled_test_delegate_below_exact_sink",
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "httpx.AsyncClient.get",
    ): "auxiliary_read_only_network",
}

# An import is evidence that the module can acquire the capability.  It is not
# a claim that every use is Bind-governed or that importing it performs I/O.
DECLARED_EFFECT_CAPABILITIES = {
    (
        "veritas_os/policy/bind_effect_reconciliation.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/bind_execution_capability.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/debate_safety_policy_runtime_shadow.py",
        "os",
    ): "process_launch_capable_but_not_used",
    (
        "veritas_os/policy/live_adapter_bind_authorization_consumption_store.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/runtime_adapter.py",
        "os",
    ): "process_launch_capable_but_not_used",
    (
        "veritas_os/policy/sandbox_bind_execution.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_credential_resolution.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "asyncio",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/sandbox_receipt_outcome.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "asyncio",
    ): "auxiliary_read_only_network",
    ("veritas_os/policy/sandbox_recovery.py", "asyncio"): "outside_v1_but_declared",
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "httpx",
    ): "auxiliary_read_only_network",
    ("veritas_os/policy/webhook_bind_adapter.py", "socket"): "auxiliary_dns_resolution",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.HTTPRedirectHandler",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.Request",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.build_opener",
    ): "governed_v1_effect_transport",
}

# Counts are deliberate: unlike a set of (path, usage), this inventory changes
# when a second copy of an already-reviewed call is added to a production file.
# It is populated below from the reviewed policy tree and kept as source data,
# not inferred at proof time.
DECLARED_EFFECT_USAGES: dict[tuple[str, str], tuple[int, str]] = {
    ("veritas_os/policy/bind_effect_reconciliation.py", "asyncio.Lock"): (
        1,
        "synchronization_only",
    ),
    ("veritas_os/policy/bind_execution_capability.py", "asyncio.current_task"): (
        1,
        "synchronization_only",
    ),
    ("veritas_os/policy/debate_safety_policy_runtime_shadow.py", "os.getenv"): (
        1,
        "process_capable_but_non_effect_use",
    ),
    (
        "veritas_os/policy/live_adapter_bind_authorization_consumption_store.py",
        "asyncio.Lock",
    ): (1, "synchronization_only"),
    ("veritas_os/policy/runtime_adapter.py", "os.environ.get"): (
        1,
        "process_capable_but_non_effect_use",
    ),
    ("veritas_os/policy/runtime_adapter.py", "os.getenv"): (
        1,
        "process_capable_but_non_effect_use",
    ),
    ("veritas_os/policy/sandbox_bind_execution.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/sandbox_bind_execution.py", "asyncio.timeout"): (
        1,
        "synchronization_only",
    ),
    ("veritas_os/policy/sandbox_credential_resolution.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/sandbox_credential_resolution.py", "asyncio.timeout"): (
        2,
        "synchronization_only",
    ),
    ("veritas_os/policy/sandbox_https_transport.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/sandbox_https_transport.py", "asyncio.open_connection"): (
        1,
        "governed_v1_effect",
    ),
    ("veritas_os/policy/sandbox_https_transport.py", "asyncio.timeout"): (
        1,
        "synchronization_only",
    ),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(asyncio.open_connection)[0].readexactly",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(asyncio.open_connection)[0].readuntil",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(asyncio.open_connection)[1].drain",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(asyncio.open_connection)[1].transport.abort",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(asyncio.open_connection)[1].write",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "result(result(asyncio.open_connection)[0].readexactly).decode",
    ): (1, "reviewed_non_effect_usage"),
    ("veritas_os/policy/sandbox_receipt_outcome.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/sandbox_reconciliation.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/sandbox_reconciliation.py", "asyncio.open_connection"): (
        1,
        "auxiliary_read_only_network",
    ),
    ("veritas_os/policy/sandbox_reconciliation.py", "asyncio.timeout"): (
        1,
        "synchronization_only",
    ),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "result(asyncio.open_connection)[1].drain",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "result(asyncio.open_connection)[1].transport.abort",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "result(asyncio.open_connection)[1].write",
    ): (1, "auxiliary_read_only_network"),
    ("veritas_os/policy/sandbox_recovery.py", "asyncio.CancelledError"): (
        1,
        "reviewed_non_effect_usage",
    ),
    ("veritas_os/policy/trusted_https_reconciliation.py", "httpx.AsyncClient"): (
        1,
        "capability_factory",
    ),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "httpx.AsyncClient.get",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "result(httpx.AsyncClient.get).json",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "result(httpx.AsyncClient.get).raise_for_status",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "result(result(urllib.request.build_opener).open).headers.items",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "result(result(urllib.request.build_opener).open).read",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "result(urllib.request.build_opener).open",
    ): (1, "governed_v1_effect"),
    ("veritas_os/policy/webhook_bind_adapter.py", "socket.getaddrinfo"): (
        1,
        "auxiliary_read_only_network",
    ),
    ("veritas_os/policy/webhook_bind_adapter.py", "urllib.request.Request"): (
        1,
        "capability_factory",
    ),
    ("veritas_os/policy/webhook_bind_adapter.py", "urllib.request.build_opener"): (
        1,
        "capability_factory",
    ),
}

# This outer inventory is intentionally independent of effect-family knowledge.
# A new non-VERITAS dependency therefore requires review even when this scanner
# does not yet understand that dependency's effect mechanisms.

# Lexical context is an authority-bearing inventory dimension; source lines are
# retained only as evidence and deliberately do not participate in equality.
DECLARED_EFFECT_USAGE_CONTEXTS: dict[tuple[str, str, str], tuple[int, str]] = {
    (
        "veritas_os/policy/bind_effect_reconciliation.py",
        "InMemoryAtomicEffectStateStore.__init__",
        "asyncio.Lock",
    ): (1, "synchronization_only"),
    (
        "veritas_os/policy/bind_execution_capability.py",
        "_task_identity",
        "asyncio.current_task",
    ): (1, "synchronization_only"),
    (
        "veritas_os/policy/debate_safety_policy_runtime_shadow.py",
        "build_debate_safety_policy_shadow_diagnostics_from_env",
        "os.getenv",
    ): (1, "process_capable_but_non_effect_use"),
    (
        "veritas_os/policy/live_adapter_bind_authorization_consumption_store.py",
        "InMemoryAtomicAuthorizationConsumptionStore.__init__",
        "asyncio.Lock",
    ): (1, "synchronization_only"),
    ("veritas_os/policy/runtime_adapter.py", "_ed25519_required", "os.getenv"): (
        1,
        "process_capable_but_non_effect_use",
    ),
    (
        "veritas_os/policy/runtime_adapter.py",
        "_resolve_verification_public_key",
        "os.environ.get",
    ): (1, "process_capable_but_non_effect_use"),
    (
        "veritas_os/policy/sandbox_bind_execution.py",
        "execute_sandbox_bind",
        "asyncio.timeout",
    ): (1, "synchronization_only"),
    (
        "veritas_os/policy/sandbox_bind_execution.py",
        "execute_sandbox_bind",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_credential_resolution.py",
        "prepare_and_resolve_sandbox_credential",
        "asyncio.timeout",
    ): (2, "synchronization_only"),
    (
        "veritas_os/policy/sandbox_credential_resolution.py",
        "prepare_and_resolve_sandbox_credential",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "asyncio.timeout",
    ): (1, "synchronization_only"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "asyncio.open_connection",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "result(asyncio.open_connection)[1].write",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "result(asyncio.open_connection)[1].drain",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "result(asyncio.open_connection)[1].transport.abort",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "_read_bounded_response",
        "result(asyncio.open_connection)[0].readuntil",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "_read_bounded_response",
        "result(asyncio.open_connection)[0].readexactly",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "_parse_operation",
        "result(result(asyncio.open_connection)[0].readexactly).decode",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_receipt_outcome.py",
        "publish_sandbox_receipts",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "asyncio.timeout",
    ): (1, "synchronization_only"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "asyncio.open_connection",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "result(asyncio.open_connection)[1].write",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "result(asyncio.open_connection)[1].drain",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "result(asyncio.open_connection)[1].transport.abort",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/sandbox_recovery.py",
        "recover_sandbox_attempt",
        "asyncio.CancelledError",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "TrustedHttpsReconciliationVerifier._retrieve",
        "httpx.AsyncClient",
    ): (1, "capability_factory"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "TrustedHttpsReconciliationVerifier._retrieve",
        "httpx.AsyncClient.get",
    ): (1, "auxiliary_read_only_network"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "TrustedHttpsReconciliationVerifier._retrieve",
        "result(httpx.AsyncClient.get).raise_for_status",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "TrustedHttpsReconciliationVerifier._retrieve",
        "result(httpx.AsyncClient.get).json",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "urllib.request.Request",
    ): (1, "capability_factory"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "urllib.request.build_opener",
    ): (1, "capability_factory"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "result(urllib.request.build_opener).open",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "result(result(urllib.request.build_opener).open).read",
    ): (1, "governed_v1_effect"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "result(result(urllib.request.build_opener).open).headers.items",
    ): (1, "reviewed_non_effect_usage"),
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_resolve_host",
        "socket.getaddrinfo",
    ): (1, "auxiliary_read_only_network"),
}

DECLARED_EFFECT_SINK_CONTEXTS: dict[tuple[str, str, str], str] = {
    (
        "veritas_os/policy/bundle.py",
        "create_bundle_archive",
        "archive_path.open",
    ): "local_file_io",
    (
        "veritas_os/policy/bundle.py",
        "create_bundle_archive",
        "tarfile.open",
    ): "local_file_io",
    ("veritas_os/policy/bundle.py", "create_bundle_archive", "open"): "local_file_io",
    (
        "veritas_os/policy/sandbox_event_service.py",
        "create_sandbox_event_service",
        "app.post",
    ): "route_registration_not_dispatch",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "asyncio.open_connection",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "SandboxHTTPSTransport.send_once",
        "writer.write",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "asyncio.open_connection",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "reconcile_sandbox_effect",
        "writer.write",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "TrustedHttpsReconciliationVerifier._retrieve",
        "httpx.AsyncClient.get",
    ): "auxiliary_read_only_network",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "WebhookBindAdapter._request",
        "transport.request",
    ): "registered_webhook_dispatch_to_exact_sink",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "self._delegate.request",
    ): "controlled_test_delegate_below_exact_sink",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "_UrllibWebhookTransport.request",
        "opener.open",
    ): "registered_webhook_action_or_compensation",
}

DECLARED_REVIEWED_DEPENDENCIES = {
    "__future__": "stdlib_non_effect",
    "abc": "stdlib_non_effect",
    "asyncio": "effect_capable",
    "base64": "stdlib_non_effect",
    "binascii": "stdlib_non_effect",
    "concurrent.futures": "stdlib_non_effect",
    "contextlib": "stdlib_non_effect",
    "contextvars": "stdlib_non_effect",
    "cryptography.exceptions": "non_effect_support",
    "cryptography.hazmat.primitives": "non_effect_support",
    "cryptography.hazmat.primitives.asymmetric.ed25519": "non_effect_support",
    "dataclasses": "stdlib_non_effect",
    "datetime": "stdlib_non_effect",
    "enum": "stdlib_non_effect",
    "fastapi": "non_effect_support",
    "fastapi.responses": "non_effect_support",
    "functools": "stdlib_non_effect",
    "gzip": "local_io_capable",
    "hashlib": "stdlib_non_effect",
    "hmac": "stdlib_non_effect",
    "httpx": "effect_capable",
    "ipaddress": "stdlib_non_effect",
    "json": "stdlib_non_effect",
    "logging": "stdlib_non_effect",
    "math": "stdlib_non_effect",
    "os": "process_launch_capable",
    "pathlib": "local_io_capable",
    "psycopg.types.json": "non_effect_support",
    "pydantic": "non_effect_support",
    "re": "stdlib_non_effect",
    "secrets": "stdlib_non_effect",
    "socket": "effect_capable",
    "ssl": "non_effect_support",
    "tarfile": "local_io_capable",
    "threading": "stdlib_non_effect",
    "typing": "stdlib_non_effect",
    "urllib.error": "non_effect_support",
    "urllib.parse": "non_effect_support",
    "urllib.request": "effect_capable",
    "uuid": "stdlib_non_effect",
    "weakref": "stdlib_non_effect",
    "yaml": "non_effect_support",
}

# Compatibility name for callers of the historical one-inventory interface.
DECLARED_EFFECT_CANDIDATES = DECLARED_EFFECT_SINKS

_CAPABILITY_MODULES = {
    "aiohttp",
    "asyncio",
    "http.client",
    "httpx",
    "os",
    "requests",
    "socket",
    "subprocess",
    "urllib.request",
}
_NETWORK_METHODS = {
    "connect",
    "connect_ex",
    "create_connection",
    "create_server",
    "delete",
    "get",
    "open",
    "open_connection",
    "patch",
    "post",
    "put",
    "request",
    "send",
    "sendall",
    "sendto",
    "start_server",
    "stream",
    "urlopen",
}
_PROCESS_METHODS = {
    "Popen",
    "call",
    "check_call",
    "check_output",
    "popen",
    "run",
    "system",
}
_PRESERVED_SINKS = {
    "app.post",
    "archive_path.open",
    "open",
    "opener.open",
    "self._delegate.request",
    "tarfile.open",
    "transport.request",
    "writer.write",
}
MATRIX_CASES = (
    "direct adapter invocation",
    "direct helper invocation",
    "direct transport invocation",
    "fake Permit",
    "reconstructed Permit",
    "serialized Permit",
    "Permit replay",
    "concurrent Permit use",
    "leaked consumed Permit",
    "wrong operation",
    "wrong resource",
    "changed credential identity",
    "stale/expired authorization",
    "consumed authorization",
    "alternate adapter",
    "unregistered subclass",
    "wrapper/proxy",
    "alternate factory implementation",
    "duplicate coverage",
    "ambiguous coverage",
    "registry/runtime mismatch",
    "undeclared effect sink",
    "ACTION Permit used for COMPENSATION",
    "direct COMPENSATION Permit mint",
    "fake CompensationEligibilityGrant",
    "reconstructed Grant",
    "Grant replay",
    "concurrent Grant consumption",
    "cross-ACTION Grant reuse",
    "compensation endpoint mutation",
    "compensation payload mutation",
    "recovery ACTION remint attempt",
    "recovery Grant fabrication",
    "valid P2/H(P2) against Permit(P1)",
    "post-validation P1-to-P2 TOCTOU attempt",
    "exact outbound representation equality",
    "legitimate ACTION",
    "legitimate COMPENSATION",
)

MATRIX_CASE_TO_PYTEST_NODE = {
    "direct adapter invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_adapter_invocation_has_zero_external_post",
    "direct helper invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_helper_invocation_has_zero_external_post",
    "direct transport invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_transport_invocation_has_zero_external_post",
    "fake Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_fake_permit_is_rejected",
    "reconstructed Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_reconstructed_permit_is_rejected",
    "serialized Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_serialized_permit_is_rejected",
    "Permit replay": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_permit_replay_is_rejected",
    "concurrent Permit use": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_permit_atomic_consumption_has_exactly_one_winner",
    "leaked consumed Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_leaked_consumed_permit_reference_is_rejected",
    "wrong operation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[wrong-operation]",
    "wrong resource": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[wrong-resource]",
    "changed credential identity": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[changed-credential-identity]",
    "stale/expired authorization": "veritas_os/tests/test_live_adapter_bind_authorization_consumption.py::test_expired_authorization_fails_before_consumption",
    "consumed authorization": "veritas_os/tests/test_live_adapter_bind_authorization_consumption.py::test_failure_after_consumption_never_releases_authorization",
    "alternate adapter": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_alternate_adapter_is_rejected",
    "unregistered subclass": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_unregistered_subclass_is_rejected",
    "wrapper/proxy": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_wrapper_proxy_is_rejected",
    "alternate factory implementation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_alternate_factory_implementation_is_rejected",
    "duplicate coverage": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_duplicate_coverage_is_rejected",
    "ambiguous coverage": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_ambiguous_coverage_is_rejected",
    "registry/runtime mismatch": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_registry_runtime_mismatch_is_rejected",
    "undeclared effect sink": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_undeclared_effect_sink_breaks_exact_inventory_equality",
    "ACTION Permit used for COMPENSATION": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_action_permit_cannot_authorize_compensation",
    "direct COMPENSATION Permit mint": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_compensation_permit_mint_is_rejected",
    "fake CompensationEligibilityGrant": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_fake_compensation_grant_is_rejected",
    "reconstructed Grant": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_reconstructed_compensation_grant_is_rejected",
    "Grant replay": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_grant_replay_is_rejected",
    "concurrent Grant consumption": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_concurrent_grant_consumption_has_exactly_one_winner",
    "cross-ACTION Grant reuse": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_cross_action_grant_reuse_is_rejected",
    "compensation endpoint mutation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_compensation_endpoint_mutation_is_rejected",
    "compensation payload mutation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_compensation_payload_mutation_is_rejected",
    "recovery ACTION remint attempt": "veritas_os/tests/test_sandbox_recovery.py::test_pre_dispatch_crash_closes_no_effect_without_reader_or_resend",
    "recovery Grant fabrication": "veritas_os/tests/test_sandbox_recovery.py::test_lookup_absence_remains_unknown_and_never_posts",
    "valid P2/H(P2) against Permit(P1)": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_valid_p2_cannot_replace_frozen_p1",
    "post-validation P1-to-P2 TOCTOU attempt": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_post_validation_toctou_dispatches_frozen_p1",
    "exact outbound representation equality": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_legitimate_webhook_action_sends_exact_frozen_bytes",
    "legitimate ACTION": "veritas_os/tests/test_sandbox_https_transport.py::test_single_exact_post_and_observations[201-HTTP_201_MATCHING_ACK]",
    "legitimate COMPENSATION": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_bind_core_transition_mints_exactly_one_compensation",
}


def _expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _expression_name(node.func)
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _canonical_name(name: str, aliases: dict[str, str]) -> str:
    head, separator, tail = name.partition(".")
    canonical = aliases.get(head, head)
    return canonical + (separator + tail if separator else "")


def _is_capability_import(name: str) -> bool:
    return any(
        name == family or name.startswith(f"{family}.")
        for family in _CAPABILITY_MODULES
    )


def _is_effect_sink(name: str) -> bool:
    if name in _PRESERVED_SINKS:
        return True
    head, _, tail = name.partition(".")
    terminal = name.rsplit(".", 1)[-1]
    if head == "socket":
        return terminal in _NETWORK_METHODS or name == "socket.socket"
    if head in {"aiohttp", "httpx", "requests", "urllib"}:
        return terminal in _NETWORK_METHODS
    if name.startswith("http.client.") or name.startswith("asyncio."):
        return terminal in _NETWORK_METHODS
    if head == "subprocess":
        return terminal in _PROCESS_METHODS
    if head == "os":
        return terminal in _PROCESS_METHODS or terminal.startswith(("exec", "spawn"))
    return False


class _EffectVisitor(ast.NodeVisitor):
    """Resolve bounded effect provenance with isolated lexical Name frames.

    None bindings explicitly shadow outer names. Class-body bindings are not
    bare-name parents of methods. Only explicitly reviewed direct helper flows
    receive argument/return provenance; arbitrary interprocedural flow is unsupported.
    """

    def __init__(
        self, relative: str, helper_names: frozenset[str] | None = None
    ) -> None:
        self.relative = relative
        # Explicitly reviewed, same-module direct helper calls only. Provenance
        # comes from actual call arguments and return expressions, never names.
        self.helper_names = (
            helper_names
            if helper_names is not None
            else (
                frozenset(
                    {"_read_observation", "_read_bounded_response", "_parse_operation"}
                )
                if relative == "veritas_os/policy/sandbox_https_transport.py"
                else frozenset()
            )
        )
        self.helper_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.parameter_defaults: dict[int, tuple[dict[str, str | None], set[str]]] = {}
        self.helper_stack: tuple[str, ...] = ()
        self.return_provenances: list[tuple[str | None, ...]] = []
        self.call_evidence: set[tuple[int, str, str]] = set()
        # Kept separate from the live source-order module frames. Bodies receive
        # copies, so local traversal cannot mutate this completed binding snapshot.
        self.module_runtime: tuple[dict[str, str], dict[str, str | None]] | None = None
        self.context_stack: list[str] = []
        self.alias_frames: list[tuple[str, dict[str, str]]] = [("module", {})]
        self.name_frames: list[dict[str, str | None]] = [{}]
        self.attribute_instances: dict[tuple[str, str], str] = {}
        self.dependencies: list[dict[str, object]] = []
        self.capabilities: list[dict[str, object]] = []
        self.usages: list[dict[str, object]] = []
        self.sinks: list[dict[str, object]] = []

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        collector = _ModuleBindingCollector(self.relative)
        collector.visit(node)
        self.module_runtime = (
            collector.alias_frames[0][1].copy(),
            collector.name_frames[0].copy(),
        )
        self.parameter_defaults.update(collector.parameter_defaults)
        for statement in node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if statement.name in self.helper_names:
                    if statement.name in self.helper_definitions:
                        raise ValueError("duplicate reviewed helper definition")
                    self.helper_definitions[statement.name] = statement
        self.generic_visit(node)

    def _helper_result(self, call: ast.Call) -> tuple[str | None, ...] | None:
        """Resolve reviewed direct calls with explicit argument/return binding.

        No callback, method, variadic, recursive, or arbitrary call-graph inference
        is supported. Unsupported reviewed call shapes fail the inventory gate.
        """
        if not isinstance(call.func, ast.Name):
            return None
        name = call.func.id
        if name not in self.helper_definitions or self._resolve_name(call.func) != name:
            return None
        definition = self.helper_definitions[name]
        if name in self.helper_stack or len(self.helper_stack) >= 4:
            raise ValueError("reviewed helper recursion/depth is unsupported")
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            for statement in definition.body
            for node in ast.walk(statement)
        ):
            raise ValueError("nested reviewed helper definitions are unsupported")
        args = definition.args
        if args.vararg or args.kwarg or definition.decorator_list:
            raise ValueError("reviewed helper signature is unsupported")
        positional = [arg.arg for arg in args.posonlyargs + args.args]
        parameters = positional + [arg.arg for arg in args.kwonlyargs]
        if len(call.args) > len(positional) or any(
            isinstance(arg, ast.Starred) for arg in call.args
        ):
            raise ValueError("reviewed helper positional binding is unsupported")
        bindings = {
            parameter: self._value_provenance(value)
            for parameter, value in zip(positional, call.args, strict=False)
        }
        for keyword in call.keywords:
            if keyword.arg not in parameters or keyword.arg in bindings:
                raise ValueError("reviewed helper keyword binding is unsupported")
            if keyword.arg in {arg.arg for arg in args.posonlyargs}:
                raise ValueError("reviewed helper positional-only parameter")
            bindings[keyword.arg] = self._value_provenance(keyword.value)
        defaults, unresolved = self.parameter_defaults.get(id(definition), ({}, set()))
        for parameter in set(parameters) - set(bindings):
            if parameter not in defaults:
                raise ValueError("reviewed helper arguments are incomplete")
            if parameter in unresolved:
                raise ValueError(
                    "reviewed helper default requires definition-time review"
                )
            bindings[parameter] = defaults[parameter]
        child = _EffectVisitor(self.relative, self.helper_names)
        child.helper_definitions = self.helper_definitions
        child.parameter_defaults = self.parameter_defaults
        child.module_runtime = self.module_runtime
        child.call_evidence = self.call_evidence
        child.helper_stack = self.helper_stack + (name,)
        child.alias_frames = [
            ("module", self.alias_frames[0][1].copy()),
            ("function", {}),
        ]
        child.name_frames = [self.name_frames[0].copy(), bindings]
        child.context_stack = [name]
        for statement in definition.body:
            child.visit(statement)
        # A definition may be reached from multiple callsites. Count each actual
        # syntactic use once per provenance, retaining conflicting provenances.
        for attribute in ("dependencies", "capabilities", "usages", "sinks"):
            destination = getattr(self, attribute)
            for row in getattr(child, attribute):
                if row not in destination:
                    destination.append(row)
        returns = set(child.return_provenances)
        if len(returns) > 1 and any(any(item for item in row) for row in returns):
            raise ValueError("ambiguous reviewed helper return provenance")
        result = next(iter(returns)) if len(returns) == 1 else None
        return result

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        if self.helper_stack:
            values = (
                node.value.elts
                if isinstance(node.value, (ast.Tuple, ast.List))
                else [node.value]
            )
            self.return_provenances.append(
                tuple(
                    self._value_provenance(value) if value is not None else None
                    for value in values
                )
            )
        self.generic_visit(node)

    def _current_qualname(self) -> str:
        return ".".join(self.context_stack) if self.context_stack else "<module>"

    def _bind_alias(self, local: str, identity: str) -> None:
        self.alias_frames[-1][1][local] = identity
        self.name_frames[-1].pop(local, None)

    def _visit_body_context(
        self,
        body: list[ast.stmt],
        name: str,
        frame_kind: str,
        initial_name_bindings: dict[str, str | None] | None = None,
    ) -> None:
        source_alias_frame = self.alias_frames[0]
        source_name_frame = self.name_frames[0]
        if frame_kind == "function" and self.module_runtime is not None:
            aliases, names = self.module_runtime
            self.alias_frames[0] = ("module", aliases.copy())
            self.name_frames[0] = names.copy()
        self.context_stack.append(name)
        self.alias_frames.append((frame_kind, {}))
        self.name_frames.append(dict(initial_name_bindings or {}))
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self.name_frames.pop()
            self.alias_frames.pop()
            self.context_stack.pop()
            self.alias_frames[0] = source_alias_frame
            self.name_frames[0] = source_name_frame

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._visit_body_context(node.body, node.name, "class")

    def _visit_function_definition(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        parameter_bindings = self._visit_parameter_defaults(node.args, id(node))
        if node.returns is not None:
            self.visit(node.returns)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._visit_body_context(node.body, node.name, "function", parameter_bindings)

    def _visit_parameter_defaults(
        self, args: ast.arguments, definition_id: int
    ) -> dict[str, str | None]:
        """Capture positional/kw-only defaults before annotations and body globals.

        Every parameter shadows outer names. Default lookup uses a state-only
        visitor, so deriving provenance cannot emit a second call evidence row.
        Unknown helper defaults are retained as unresolved and require review
        only when a reviewed call actually omits that argument.
        """
        positional = args.posonlyargs + args.args
        parameters = positional + args.kwonlyargs
        parameters += [arg for arg in (args.vararg, args.kwarg) if arg is not None]
        bindings: dict[str, str | None] = {arg.arg: None for arg in parameters}
        pairs = list(
            zip(
                positional[len(positional) - len(args.defaults) :],
                args.defaults,
                strict=True,
            )
        )
        pairs.extend(zip(args.kwonlyargs, args.kw_defaults, strict=True))
        defaults: dict[str, str | None] = {}
        unresolved: set[str] = set()
        for arg, value in pairs:
            if value is None:
                continue
            self.visit(value)
            lookup = _ModuleBindingCollector(self.relative)
            lookup.alias_frames = [
                (kind, frame.copy()) for kind, frame in self.alias_frames
            ]
            lookup.name_frames = [frame.copy() for frame in self.name_frames]
            lookup.context_stack = self.context_stack.copy()
            lookup.attribute_instances = self.attribute_instances.copy()
            provenance = lookup._value_provenance(value)
            defaults[arg.arg] = bindings[arg.arg] = provenance
            # Only direct resolved provenance, literals and explicitly harmless
            # builtins constitute a safe omitted default in the bounded helper model.
            if provenance is None and not (
                isinstance(value, ast.Constant)
                or isinstance(value, ast.Name)
                and value.id in {"print", "len", "str", "int", "bool", "object"}
                and not any(
                    value.id in aliases or value.id in names
                    for (_, aliases), names in zip(
                        self.alias_frames, self.name_frames, strict=True
                    )
                )
            ):
                unresolved.add(arg.arg)
        self.parameter_defaults[definition_id] = (defaults, unresolved)
        # Annotation NamedExpr writes may change the outer environment, but
        # cannot change the default identities already captured above. The
        # state-only collector inherits this same definition-time ordering.
        for arg in parameters:
            self.visit(arg)
        return bindings

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function_definition(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function_definition(node)

    def _add_dependency(self, identity: str, line: int) -> None:
        if not identity.startswith("veritas_os"):
            self.dependencies.append(
                {
                    "path": self.relative,
                    "dependency": identity,
                    "line": line,
                }
            )

    def _add_capability(self, identity: str, line: int) -> None:
        self.capabilities.append(
            {
                "path": self.relative,
                "capability": identity,
                "line": line,
            }
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for imported in node.names:
            local = imported.asname or imported.name.split(".", 1)[0]
            self._bind_alias(
                local,
                imported.name if imported.asname else imported.name.split(".", 1)[0],
            )
            if _is_capability_import(imported.name):
                self._add_capability(imported.name, node.lineno)
            self._add_dependency(imported.name, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module is None or node.level:
            return
        self._add_dependency(node.module, node.lineno)
        for imported in node.names:
            identity = f"{node.module}.{imported.name}"
            self._bind_alias(imported.asname or imported.name, identity)
            if _is_capability_import(identity):
                self._add_capability(identity, node.lineno)

    @staticmethod
    def _unwrap_await(value: ast.AST) -> ast.AST:
        return value.value if isinstance(value, ast.Await) else value

    def _resolve_supported_dynamic_import_result(self, node: ast.AST) -> str | None:
        """Resolve literal, direct import results without emitting evidence.

        Only the one-positional-argument form is supported here. In particular,
        relative imports, fromlist overrides and arbitrary call roots are not
        inferred. Builtin __import__ returns the top-level package for dotted
        names; import_module returns the requested module.
        """
        if not isinstance(node, ast.Call) or len(node.args) != 1 or node.keywords:
            return None
        argument = node.args[0]
        if not isinstance(argument, ast.Constant) or not isinstance(
            argument.value, str
        ):
            return None
        if not argument.value or not all(
            part.isidentifier() for part in argument.value.split(".")
        ):
            return None
        root = node.func
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return None
        canonical = self._resolve_name(node.func)
        if canonical == "__import__":
            return argument.value.split(".", 1)[0]
        if canonical == "importlib.import_module" and any(
            root.id in aliases or root.id in names
            for (_, aliases), names in zip(
                self.alias_frames, self.name_frames, strict=True
            )
        ):
            return argument.value
        return None

    def _dynamic_import_attribute(self, node: ast.AST) -> str | None:
        """Resolve direct or NamedExpr-wrapped literal import roots, state only."""
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not parts:
            return None
        if isinstance(node, ast.NamedExpr):
            # Resolve only the value, never the enclosing Attribute. Restrict
            # this composition to the existing literal-import result family.
            module = self._resolve_supported_dynamic_import_result(node.value)
            if module is not None:
                self._bind_provenance(node.target, module)
            else:
                self._clear_provenance(node.target)
        else:
            module = self._resolve_supported_dynamic_import_result(node)
        return ".".join([module, *reversed(parts)]) if module is not None else None

    def _resolve_name(self, node: ast.AST) -> str:
        imported_attribute = self._dynamic_import_attribute(node)
        if imported_attribute is not None:
            return imported_attribute
        if isinstance(node, ast.NamedExpr):
            return self._namedexpr_provenance(node) or ""
        raw = _expression_name(node)
        attribute_parts = raw.split(".")
        scope = self._current_qualname()
        for end in range(len(attribute_parts), 1, -1):
            prefix = ".".join(attribute_parts[:end])
            provenance = self.attribute_instances.get((scope, prefix))
            if provenance is not None:
                suffix = ".".join(attribute_parts[end:])
                return provenance + (f".{suffix}" if suffix else "")
        head, separator, tail = raw.partition(".")
        function_body = self.alias_frames[-1][0] == "function"
        for (kind, aliases), names in reversed(
            list(zip(self.alias_frames, self.name_frames, strict=True))
        ):
            if function_body and kind == "class":
                continue
            if head in names:
                # None is an explicit local shadow, not a missing binding.
                provenance = names[head]
                return (
                    provenance + (separator + tail if separator else "")
                    if provenance is not None
                    else ""
                )
            if head in aliases:
                return aliases[head] + (separator + tail if separator else "")
        if self.module_runtime is not None:
            runtime_aliases, runtime_names = self.module_runtime
            if head in runtime_aliases or head in runtime_names:
                # A name known only in the completed environment is not yet
                # available to a definition-time/source-order expression.
                return ""
        return raw

    def _value_provenance(self, value: ast.AST) -> str | None:
        value = self._unwrap_await(value)
        imported_module = self._resolve_supported_dynamic_import_result(value)
        if imported_module is not None:
            return imported_module
        if isinstance(value, ast.Call):
            result = self._helper_result(value)
            if result is not None:
                return result[0] if len(result) == 1 else None
        expression = value.func if isinstance(value, ast.Call) else value
        canonical = self._resolve_name(expression)
        if canonical.endswith((".get_event_loop", ".get_running_loop")):
            return "asyncio.loop"
        if canonical == "socket.socket" or canonical.endswith(
            (
                ".Client",
                ".AsyncClient",
                ".ClientSession",
                ".HTTPConnection",
                ".HTTPSConnection",
                ".Session",
            )
        ):
            return canonical
        if isinstance(value, ast.Call) and self._has_effect_provenance(canonical):
            return f"result({canonical})"
        if self._has_effect_provenance(canonical):
            return canonical
        return None

    def _bind_provenance(self, target: ast.AST, provenance: str) -> None:
        if isinstance(target, ast.Name):
            self.name_frames[-1][target.id] = provenance
            return
        identity = self._attribute_identity(target)
        if identity is not None:
            self.attribute_instances[(self._current_qualname(), identity)] = provenance
        elif isinstance(target, (ast.Tuple, ast.List)):
            for index, element in enumerate(target.elts):
                self._bind_provenance(element, f"{provenance}[{index}]")

    @staticmethod
    def _attribute_identity(target: ast.AST) -> str | None:
        """Return a direct attribute chain rooted in a syntactic name."""
        if not isinstance(target, ast.Attribute):
            return None
        parts = [target.attr]
        value = target.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if not isinstance(value, ast.Name):
            return None
        parts.append(value.id)
        return ".".join(reversed(parts))

    def _clear_provenance(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.name_frames[-1][target.id] = None
            return
        identity = self._attribute_identity(target)
        if identity is not None:
            self.attribute_instances.pop((self._current_qualname(), identity), None)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._clear_provenance(element)

    def _namedexpr_provenance(self, node: ast.NamedExpr) -> str | None:
        provenance = self._value_provenance(node.value)
        if provenance is not None:
            self._bind_provenance(node.target, provenance)
        else:
            self._clear_provenance(node.target)
        return provenance

    def _record_instance(self, target: ast.AST, value: ast.AST) -> None:
        unwrapped = self._unwrap_await(value)
        if isinstance(unwrapped, ast.Call) and isinstance(
            target, (ast.Tuple, ast.List)
        ):
            result = self._helper_result(unwrapped)
            if result is not None:
                if len(result) != len(target.elts) or any(
                    isinstance(item, ast.Starred) for item in target.elts
                ):
                    raise ValueError("reviewed helper return unpacking is unsupported")
                for element, provenance in zip(target.elts, result, strict=True):
                    if provenance is None:
                        self._clear_provenance(element)
                    else:
                        self._bind_provenance(element, provenance)
                return
        if (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(target.elts) == len(value.elts)
            and not any(isinstance(element, ast.Starred) for element in target.elts)
        ):
            for target_element, value_element in zip(
                target.elts, value.elts, strict=True
            ):
                self._record_instance(target_element, value_element)
            return
        provenance = self._value_provenance(value)
        if provenance is not None:
            self._bind_provenance(target, provenance)
        else:
            self._clear_provenance(target)

    @staticmethod
    def _has_effect_provenance(canonical: str) -> bool:
        root = canonical.split(".", 1)[0]
        if root.startswith("result("):
            return True
        return _is_capability_import(canonical) or root in _CAPABILITY_MODULES

    def _record_dynamic_import(self, target: ast.AST, value: ast.AST) -> None:
        module = self._resolve_supported_dynamic_import_result(value)
        if isinstance(target, ast.Name) and module is not None:
            self._bind_alias(target.id, module)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            self._record_instance(target, node.value)
            self._record_dynamic_import(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        if node.value is not None:
            self._record_instance(node.target, node.value)
            self._record_dynamic_import(node.target, node.value)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802
        self._namedexpr_provenance(node)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        for item in node.items:
            if item.optional_vars is not None:
                self._record_instance(item.optional_vars, item.context_expr)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._helper_result(node)
        raw = _expression_name(node.func)
        canonical = self._resolve_name(node.func)
        if canonical in {"__import__", "importlib.import_module"} and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                self._add_dependency(argument.value, node.lineno)
                if _is_capability_import(argument.value):
                    self._add_capability(argument.value, node.lineno)
        evidence_key = (id(node), canonical, self._current_qualname())
        already_recorded = evidence_key in self.call_evidence
        self.call_evidence.add(evidence_key)
        if self._has_effect_provenance(canonical) and not already_recorded:
            self.usages.append(
                {
                    "path": self.relative,
                    "enclosing_qualname": self._current_qualname(),
                    "usage": canonical,
                    "line": node.lineno,
                }
            )
        if not already_recorded and (
            _is_effect_sink(canonical) or raw in _PRESERVED_SINKS
        ):
            self.sinks.append(
                {
                    "path": self.relative,
                    "enclosing_qualname": self._current_qualname(),
                    "primitive": raw if raw in _PRESERVED_SINKS else canonical,
                    "line": node.lineno,
                }
            )
        self.generic_visit(node)


class _ModuleBindingReviewRequired(ValueError):
    """An effect-relevant conditional module binding requires explicit review."""


class _ModuleBindingCollector(_EffectVisitor):
    """Collect only source-ordered initialization bindings, emitting no evidence.

    Function/method and class bodies are not descended into. Definition-time
    expressions retain source order. Control-flow-dependent effect bindings are
    rejected rather than picking a branch; non-effect writes become unknown.
    """

    def __init__(self, relative: str) -> None:
        super().__init__(relative, frozenset())
        self.conditional_writes: set[str] | None = None

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        for statement in node.body:
            self.visit(statement)

    def _visit_body_context(
        self,
        body: list[ast.stmt],
        name: str,
        frame_kind: str,
        initial_name_bindings: dict[str, str | None] | None = None,
    ) -> None:
        # Only their definition-time expressions are visited by the parent hooks.
        return

    def _add_dependency(self, identity: str, line: int) -> None:
        return

    def _add_capability(self, identity: str, line: int) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Retain expression-level NamedExpr binding, never call/effect evidence.
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self.visit(node.args)

    def _resolve_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.NamedExpr):
            return super()._resolve_name(node)
        imported_attribute = self._dynamic_import_attribute(node)
        if imported_attribute is not None:
            return imported_attribute
        head = _expression_name(node).split(".", 1)[0]
        if not any(
            head in aliases or head in names
            for (_, aliases), names in zip(
                self.alias_frames, self.name_frames, strict=True
            )
        ):
            # Only the supported builtin import mechanism has an implicit binding.
            return "__import__" if head == "__import__" else ""
        return super()._resolve_name(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if isinstance(node.ctx, ast.Store):
            self._check_conditional_write(node.id, None)

    def _check_conditional_write(self, name: str, provenance: str | None) -> None:
        if self.conditional_writes is None:
            return
        old = self._resolve_name(ast.Name(id=name, ctx=ast.Load()))
        if (provenance and self._has_effect_provenance(provenance)) or (
            old and self._has_effect_provenance(old)
        ):
            raise _ModuleBindingReviewRequired(
                f"conditional effect-relevant module binding requires review: {name}"
            )
        self.conditional_writes.add(name)

    def _bind_alias(self, local: str, identity: str) -> None:
        self._check_conditional_write(local, identity)
        super()._bind_alias(local, identity)

    def _bind_provenance(self, target: ast.AST, provenance: str) -> None:
        if isinstance(target, ast.Name):
            self._check_conditional_write(target.id, provenance)
        super()._bind_provenance(target, provenance)

    def _clear_provenance(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._check_conditional_write(target.id, None)
        super()._clear_provenance(target)

    def _visit_conditional(self, node: ast.AST) -> None:
        outer_writes = self.conditional_writes
        self.conditional_writes = set()
        try:
            self.generic_visit(node)
        finally:
            writes = self.conditional_writes
            self.conditional_writes = outer_writes
            for name in writes:
                self.alias_frames[0][1].pop(name, None)
                self.name_frames[0][name] = None
            if outer_writes is not None:
                outer_writes.update(writes)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        # The test itself executes before either branch is selected.
        self.visit(node.test)
        self._visit_conditional(
            ast.Module(body=node.body + node.orelse, type_ignores=[])
        )

    visit_For = _visit_conditional
    visit_AsyncFor = _visit_conditional
    visit_While = _visit_conditional
    visit_Try = _visit_conditional
    visit_TryStar = _visit_conditional
    visit_With = _visit_conditional
    visit_AsyncWith = _visit_conditional
    visit_Match = _visit_conditional
    visit_IfExp = _visit_conditional
    visit_ListComp = _visit_conditional
    visit_SetComp = _visit_conditional
    visit_DictComp = _visit_conditional
    visit_GeneratorExp = _visit_conditional
    visit_BoolOp = _visit_conditional


def _discover_inventories(
    root: Path = POLICY_ROOT,
    helper_names: frozenset[str] | None = None,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Discover dependencies, capability imports, and sinks package-wide.

    This deliberately bounded static analysis resolves direct import aliases and
    simple assigned client/socket objects.  It is not whole-program Python
    soundness and does not resolve reflective or data-dependent dispatch.
    """
    dependencies: list[dict[str, object]] = []
    capabilities: list[dict[str, object]] = []
    usages: list[dict[str, object]] = []
    sinks: list[dict[str, object]] = []
    for source in sorted(root.rglob("*.py")):
        try:
            relative = str(source.relative_to(ROOT))
        except ValueError:
            relative = str(source.relative_to(root.parent))
        tree = ast.parse(source.read_text(encoding="utf-8"))
        visitor = _EffectVisitor(relative, helper_names)
        visitor.visit(tree)
        dependencies.extend(visitor.dependencies)
        capabilities.extend(visitor.capabilities)
        usages.extend(visitor.usages)
        sinks.extend(visitor.sinks)

    def key(item: dict[str, object]) -> tuple[str, int]:
        return str(item["path"]), int(item["line"])

    return (
        sorted(dependencies, key=key),
        sorted(capabilities, key=key),
        sorted(usages, key=key),
        sorted(sinks, key=key),
    )


def discover_inventories(
    root: Path = POLICY_ROOT,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return effect capabilities and sinks through the existing interface."""
    _, capabilities, _, sinks = _discover_inventories(root)
    return capabilities, sinks


def discover_reviewed_dependencies(
    root: Path = POLICY_ROOT,
) -> list[dict[str, object]]:
    """Return all non-VERITAS imports regardless of known effect capability."""
    dependencies, _, _, _ = _discover_inventories(root)
    return dependencies


def discover_effect_usages(root: Path = POLICY_ROOT) -> list[dict[str, object]]:
    """Return occurrence-sensitive calls through effect-capable provenance."""
    _, _, usages, _ = _discover_inventories(root)
    return usages


def discover(root: Path = POLICY_ROOT) -> list[dict[str, object]]:
    """Return the sink inventory through the historical scanner interface."""
    return discover_inventories(root)[1]


def _write(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_static_inventory_regressions() -> tuple[bool, list[dict[str, object]]]:
    """Prove representative undeclared dependencies, capabilities, and usages fail."""
    fixtures = {
        "raw_socket_create_connection": (
            "raw_socket.py",
            "import socket\nsocket.create_connection(('example.com', 443))\n",
        ),
        "imported_alias": (
            "imported_alias.py",
            "from socket import create_connection as connect_external\n"
            "connect_external(('example.com', 443))\n",
        ),
        "module_alias": (
            "module_alias.py",
            "import socket as sock\nsock.create_connection(('example.com', 443))\n",
        ),
        "automatic_new_module": (
            "unlisted_transport.py",
            "import socket\nsocket.create_connection(('example.com', 443))\n",
        ),
        "unknown_dependency": (
            "unknown_dependency.py",
            "import urllib3\nurllib3.PoolManager()\n",
        ),
        "unknown_dependency_alias": (
            "unknown_dependency_alias.py",
            "import urllib3 as u3\nu3.PoolManager()\n",
        ),
        "reviewed_asyncio_near_miss": (
            "reviewed_asyncio.py",
            "import asyncio\nasyncio.Lock()\n",
        ),
        "declared_capability_undeclared_udp_usage": (
            "reviewed_asyncio.py",
            "import asyncio\n\n"
            "async def undeclared_external_effect():\n"
            "    loop = asyncio.get_running_loop()\n"
            "    transport, _ = await loop.create_datagram_endpoint(\n"
            "        asyncio.DatagramProtocol,\n"
            "        remote_addr=('example.com', 9999),\n"
            "    )\n"
            "    transport.sendto(b'effect')\n",
        ),
        "reviewed_location_baseline": (
            "reviewed_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def send_once(self):\n"
            "        await asyncio.open_connection('example.com', 443)\n",
        ),
        "reviewed_location_relocated": (
            "reviewed_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def _direct_effect(self):\n"
            "        await asyncio.open_connection('example.com', 443)\n\n"
            "    async def send_once(self):\n"
            "        return await self._direct_effect()\n",
        ),
        "sandbox_location_baseline": (
            "reviewed_transport.py",
            "import asyncio\n\n"
            "class SandboxHTTPSTransport:\n"
            "    async def send_once(self):\n"
            "        reader, writer = await asyncio.open_connection(\n"
            "            'example.com', 443)\n"
            "        writer.write(b'effect')\n"
            "        await writer.drain()\n",
        ),
        "sandbox_location_relocated": (
            "reviewed_transport.py",
            "import asyncio\n\n"
            "class SandboxHTTPSTransport:\n"
            "    async def _unguarded_effect(self):\n"
            "        reader, writer = await asyncio.open_connection(\n"
            "            'example.com', 443)\n"
            "        writer.write(b'effect')\n"
            "        await writer.drain()\n\n"
            "    async def send_once(self):\n"
            "        return await self._unguarded_effect()\n",
        ),
        "definition_time_body_baseline": (
            "reviewed_transport.py",
            "import socket\n\n"
            "class Transport:\n"
            "    def send_once(self):\n"
            "        socket.create_connection(('example.com', 443))\n",
        ),
        "definition_time_method_default": (
            "reviewed_transport.py",
            "import socket\n\n"
            "class Transport:\n"
            "    def send_once(\n"
            "        self,\n"
            "        connection=socket.create_connection(\n"
            "            ('example.com', 443)),\n"
            "    ):\n"
            "        pass\n",
        ),
        "definition_time_module_default": (
            "reviewed_transport.py",
            "import socket\n\n"
            "def send_once(\n"
            "    connection=socket.create_connection(('example.com', 443)),\n"
            "):\n"
            "    pass\n",
        ),
        "direct_attribute_callable": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def _unguarded_effect(self):\n"
            "        self._open = asyncio.open_connection\n"
            "        reader, writer = await self._open(\n"
            "            'example.com', 443)\n"
            "        writer.writelines([b'effect'])\n"
            "        await writer.drain()\n",
        ),
        "direct_attribute_non_effect_near_miss": (
            "attribute_transport.py",
            "class Transport:\n    def label(self):\n        self._label = 'network'\n",
        ),
        "direct_attribute_callable_near_miss": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def send(self):\n"
            "        self._open = asyncio.open_connection\n"
            "        await self._open('example.com', 443)\n",
        ),
        "direct_attribute_object_factory": (
            "attribute_transport.py",
            "import httpx\n\n"
            "class Transport:\n"
            "    async def send(self):\n"
            "        self._client = httpx.AsyncClient()\n"
            "        await self._client.post('https://example.com')\n",
        ),
        "direct_attribute_rebinding_clears": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def send(self, harmless_value):\n"
            "        self._open = asyncio.open_connection\n"
            "        self._open = harmless_value\n"
            "        await self._open('example.com', 443)\n",
        ),
        "direct_attribute_scope_bounded": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    def configure(self):\n"
            "        self._open = asyncio.open_connection\n\n"
            "    async def send(self):\n"
            "        await self._open('example.com', 443)\n",
        ),
        "direct_attribute_tuple_pairwise": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def send(self):\n"
            "        (self._open,) = (asyncio.open_connection,)\n"
            "        await self._open('example.com', 443)\n",
        ),
        "direct_attribute_list_pairwise": (
            "attribute_transport.py",
            "import asyncio\n\n"
            "class Transport:\n"
            "    async def send(self):\n"
            "        [self._open] = [asyncio.open_connection]\n"
            "        await self._open('example.com', 443)\n",
        ),
        "direct_attribute_pairwise_non_effect_near_miss": (
            "attribute_transport.py",
            "class Transport:\n"
            "    async def send(self):\n"
            "        (self._label,) = ('network',)\n"
            "        await self._label()\n",
        ),
        "namedexpr_immediate_invocation": (
            "namedexpr_transport.py",
            "import asyncio\n\n"
            "async def effect():\n"
            "    reader, writer = await (\n"
            "        open_fn := asyncio.open_connection\n"
            "    )('example.com', 443)\n"
            "    writer.writelines([b'effect'])\n"
            "    await writer.drain()\n",
        ),
        "namedexpr_non_effect_near_miss": (
            "namedexpr_transport.py",
            "if (label := 'network'):\n    pass\n",
        ),
        "namedexpr_rebinding_clears": (
            "namedexpr_transport.py",
            "import asyncio\n\n"
            "async def effect(harmless_callable):\n"
            "    (open_fn := asyncio.open_connection)\n"
            "    (open_fn := harmless_callable)\n"
            "    await open_fn('example.com', 443)\n",
        ),
        "namedexpr_later_invocation": (
            "namedexpr_transport.py",
            "import asyncio\n\n"
            "async def effect():\n"
            "    (open_fn := asyncio.open_connection)\n"
            "    await open_fn('example.com', 443)\n",
        ),
        "lexical_alias_local_poisoning_attack": (
            "alias_transport.py",
            "import asyncio\n"
            "import json\n\n"
            "def scanner_shadow():\n"
            "    import json as asyncio\n\n"
            "async def undeclared_external_effect():\n"
            "    reader, writer = await asyncio.open_connection(\n"
            "        'example.com', 443)\n"
            "    writer.writelines([b'effect'])\n"
            "    await writer.drain()\n",
        ),
        "lexical_alias_sibling_scope_isolation": (
            "alias_transport.py",
            "import asyncio\n"
            "import json\n\n"
            "def configure():\n"
            "    import json as asyncio\n"
            "    asyncio.dumps({})\n\n"
            "async def send():\n"
            "    await asyncio.open_connection('example.com', 443)\n",
        ),
        "lexical_alias_harmless_near_miss": (
            "alias_transport.py",
            "import json\n\n"
            "def helper():\n"
            "    import json as parser\n"
            "    parser.dumps({})\n",
        ),
        "lexical_alias_method_scope_isolation": (
            "alias_transport.py",
            "import asyncio\n"
            "import json\n\n"
            "class A:\n"
            "    def configure(self):\n"
            "        import json as asyncio\n\n"
            "class B:\n"
            "    async def send(self):\n"
            "        await asyncio.open_connection('example.com', 443)\n",
        ),
        "lexical_alias_class_body_not_method_parent": (
            "alias_transport.py",
            "import asyncio\n"
            "import json\n\n"
            "class Transport:\n"
            "    import json as asyncio\n\n"
            "    async def send(self):\n"
            "        await asyncio.open_connection('example.com', 443)\n",
        ),
        "lexical_alias_importfrom_scope_isolation": (
            "alias_transport.py",
            "import asyncio\n"
            "import json\n\n"
            "def configure():\n"
            "    from json import dumps as asyncio\n"
            "    asyncio({})\n\n"
            "async def send():\n"
            "    await asyncio.open_connection('example.com', 443)\n",
        ),
        "lexical_alias_dynamic_import_scope_isolation": (
            "alias_transport.py",
            "def configure():\n"
            "    local_asyncio = __import__('asyncio')\n"
            "    local_asyncio.Lock()\n\n"
            "def harmless():\n"
            "    local_asyncio.Lock()\n",
        ),
        "lexical_name_module_preserved": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\ndef helper():\n    factory = print\nasync def sibling():\n    lock = factory()\n    await lock.acquire()\n",
        ),
        "lexical_name_reverse_isolation": (
            "name_scope.py",
            "import asyncio\ndef helper():\n    factory = asyncio.Lock\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_local_shadow": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\ndef helper():\n    factory = print\n    factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_namedexpr_clear": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\ndef helper():\n    (factory := print)\n    factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_namedexpr_bind": (
            "name_scope.py",
            "import asyncio\ndef helper():\n    (factory := asyncio.Lock)\n    factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_class_outer": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\nclass Example:\n    factory = print\n    def method(self):\n        factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_class_local": (
            "name_scope.py",
            "import asyncio\nclass Example:\n    factory = asyncio.Lock\n    factory()\n    def method(self):\n        factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_enclosing_function": (
            "name_scope.py",
            "import asyncio\ndef outer():\n    factory = asyncio.Lock\n    def inner():\n        factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_unpacking": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\ndef helper():\n    factory, other = print, print\n    factory()\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_import_shadow": (
            "name_scope.py",
            "import asyncio\nfactory = asyncio.Lock\ndef helper():\n    from json import dumps as factory\n    factory({})\ndef sibling():\n    factory()\n",
        ),
        "lexical_name_alias_shadow": (
            "name_scope.py",
            "import asyncio\nfrom asyncio import Lock as factory\ndef helper():\n    factory = print\n    factory()\ndef sibling():\n    factory()\n",
        ),
        "reviewed_helper_chain": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(client)\n",
        ),
        "reviewed_helper_unrelated_names": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(client)\n\ndef unrelated():\n    client.acquire()\n    outcome.bit_length()\n",
        ),
        "reviewed_helper_changed_argument": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(None)\n",
        ),
        "reviewed_helper_changed_return": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, None\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(client)\n",
        ),
        "reviewed_helper_keyword_arguments": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client=client)\n    consume(value=outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(client=client)\n",
        ),
        "reviewed_helper_shadowed_helper": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    middle = print\n    middle(client)\n",
        ),
        "reviewed_helper_multiple_calls": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    await middle(client)\n    await middle(client)\n",
        ),
        "reviewed_helper_uncalled_helper": (
            "reviewed_helpers.py",
            "import asyncio\nasync def leaf(client):\n    outcome = await client.acquire()\n    return 0, outcome\n\ndef consume(value):\n    value.bit_length()\n\nasync def middle(client):\n    _, outcome = await leaf(client)\n    consume(outcome)\n\nasync def entry():\n    client = asyncio.Lock()\n    pass\n",
        ),
    }
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as directory:
        policy_root = Path(directory) / "veritas_os" / "policy"
        policy_root.mkdir(parents=True)
        for name, (filename, source) in fixtures.items():
            for old_source in policy_root.glob("*.py"):
                old_source.unlink()
            (policy_root / filename).write_text(source, encoding="utf-8")
            dependencies, capabilities, usages, sinks = _discover_inventories(
                policy_root,
                helper_names=(
                    frozenset({"middle", "leaf", "consume"})
                    if name.startswith("reviewed_helper_")
                    else None
                ),
            )
            dependency_set = {str(row["dependency"]) for row in dependencies}
            capability_set = {
                (str(row["path"]), str(row["capability"])) for row in capabilities
            }
            sink_set = {(str(row["path"]), str(row["primitive"])) for row in sinks}
            usage_counter = Counter(
                (str(row["path"]), str(row["usage"])) for row in usages
            )
            usage_context_counter = Counter(
                (
                    str(row["path"]),
                    str(row["enclosing_qualname"]),
                    str(row["usage"]),
                )
                for row in usages
            )
            sink_context_counter = Counter(
                (
                    str(row["path"]),
                    str(row["enclosing_qualname"]),
                    str(row["primitive"]),
                )
                for row in sinks
            )
            canonical_socket_sink_found = any(
                primitive == "socket.create_connection" for _, primitive in sink_set
            )
            effect_inventories_rejected = capability_set != set(
                DECLARED_EFFECT_CAPABILITIES
            ) and sink_set != set(DECLARED_EFFECT_SINKS)
            dependency_rejected = dependency_set != set(DECLARED_REVIEWED_DEPENDENCIES)
            unknown_dependency = name.startswith("unknown_dependency")
            if name.startswith("definition_time_"):
                expected_qualname = {
                    "definition_time_body_baseline": "Transport.send_once",
                    "definition_time_method_default": "Transport",
                    "definition_time_module_default": "<module>",
                }[name]
                expected_context = Counter(
                    {
                        (
                            "policy/reviewed_transport.py",
                            expected_qualname,
                            "socket.create_connection",
                        ): 1
                    }
                )
                passed = usage_context_counter == expected_context
            elif name == "direct_attribute_callable":
                expected_context = Counter(
                    {
                        (
                            "policy/attribute_transport.py",
                            "Transport._unguarded_effect",
                            usage,
                        ): 1
                        for usage in (
                            "asyncio.open_connection",
                            "result(asyncio.open_connection)[1].writelines",
                            "result(asyncio.open_connection)[1].drain",
                        )
                    }
                )
                passed = (
                    dependency_set == {"asyncio"}
                    and {capability for _, capability in capability_set} == {"asyncio"}
                    and usage_context_counter == expected_context
                )
            elif name == "direct_attribute_non_effect_near_miss":
                passed = not dependencies and not capabilities and not usages
            elif name == "direct_attribute_callable_near_miss":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/attribute_transport.py",
                            "Transport.send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "direct_attribute_object_factory":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/attribute_transport.py",
                            "Transport.send",
                            "httpx.AsyncClient",
                        ): 1,
                        (
                            "policy/attribute_transport.py",
                            "Transport.send",
                            "httpx.AsyncClient.post",
                        ): 1,
                    }
                )
            elif name in {
                "direct_attribute_rebinding_clears",
                "direct_attribute_scope_bounded",
                "direct_attribute_pairwise_non_effect_near_miss",
            }:
                passed = not usages
            elif name in {
                "direct_attribute_tuple_pairwise",
                "direct_attribute_list_pairwise",
            }:
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/attribute_transport.py",
                            "Transport.send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "namedexpr_immediate_invocation":
                expected_context = Counter(
                    {
                        ("policy/namedexpr_transport.py", "effect", usage): 1
                        for usage in (
                            "asyncio.open_connection",
                            "result(asyncio.open_connection)[1].writelines",
                            "result(asyncio.open_connection)[1].drain",
                        )
                    }
                )
                passed = (
                    dependency_set == {"asyncio"}
                    and {capability for _, capability in capability_set} == {"asyncio"}
                    and usage_context_counter == expected_context
                )
            elif name == "namedexpr_non_effect_near_miss":
                passed = not dependencies and not capabilities and not usages
            elif name == "namedexpr_rebinding_clears":
                passed = not usages
            elif name == "namedexpr_later_invocation":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/namedexpr_transport.py",
                            "effect",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "lexical_alias_local_poisoning_attack":
                expected_context = Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "undeclared_external_effect",
                            usage,
                        ): 1
                        for usage in (
                            "asyncio.open_connection",
                            "result(asyncio.open_connection)[1].writelines",
                            "result(asyncio.open_connection)[1].drain",
                        )
                    }
                )
                passed = usage_context_counter == expected_context
            elif name == "lexical_alias_sibling_scope_isolation":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "lexical_alias_harmless_near_miss":
                passed = not capabilities and not usages and not sinks
            elif name == "lexical_alias_method_scope_isolation":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "B.send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "lexical_alias_class_body_not_method_parent":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "Transport.send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "lexical_alias_importfrom_scope_isolation":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "send",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
            elif name == "lexical_alias_dynamic_import_scope_isolation":
                passed = usage_context_counter == Counter(
                    {
                        (
                            "policy/alias_transport.py",
                            "configure",
                            "asyncio.Lock",
                        ): 1
                    }
                )
            elif name.startswith("lexical_name_"):
                expected_name_usages = {
                    "lexical_name_module_preserved": [
                        ("sibling", "asyncio.Lock"),
                        ("sibling", "result(asyncio.Lock).acquire"),
                    ],
                    "lexical_name_reverse_isolation": [],
                    "lexical_name_local_shadow": [("sibling", "asyncio.Lock")],
                    "lexical_name_namedexpr_clear": [("sibling", "asyncio.Lock")],
                    "lexical_name_namedexpr_bind": [("helper", "asyncio.Lock")],
                    "lexical_name_class_outer": [
                        ("Example.method", "asyncio.Lock"),
                        ("sibling", "asyncio.Lock"),
                    ],
                    "lexical_name_class_local": [("Example", "asyncio.Lock")],
                    "lexical_name_enclosing_function": [
                        ("outer.inner", "asyncio.Lock")
                    ],
                    "lexical_name_unpacking": [("sibling", "asyncio.Lock")],
                    "lexical_name_import_shadow": [("sibling", "asyncio.Lock")],
                    "lexical_name_alias_shadow": [("sibling", "asyncio.Lock")],
                }
                passed = usage_context_counter == Counter(
                    ("policy/name_scope.py", context, usage)
                    for context, usage in expected_name_usages[name]
                )
            elif name.startswith("reviewed_helper_"):
                expected_helper_usages = {
                    "reviewed_helper_chain": [
                        ("entry", "asyncio.Lock"),
                        ("leaf", "result(asyncio.Lock).acquire"),
                        ("consume", "result(result(asyncio.Lock).acquire).bit_length"),
                    ],
                    "reviewed_helper_unrelated_names": [
                        ("entry", "asyncio.Lock"),
                        ("leaf", "result(asyncio.Lock).acquire"),
                        ("consume", "result(result(asyncio.Lock).acquire).bit_length"),
                    ],
                    "reviewed_helper_changed_argument": [("entry", "asyncio.Lock")],
                    "reviewed_helper_changed_return": [
                        ("entry", "asyncio.Lock"),
                        ("leaf", "result(asyncio.Lock).acquire"),
                    ],
                    "reviewed_helper_keyword_arguments": [
                        ("entry", "asyncio.Lock"),
                        ("leaf", "result(asyncio.Lock).acquire"),
                        ("consume", "result(result(asyncio.Lock).acquire).bit_length"),
                    ],
                    "reviewed_helper_shadowed_helper": [("entry", "asyncio.Lock")],
                    "reviewed_helper_multiple_calls": [
                        ("entry", "asyncio.Lock"),
                        ("leaf", "result(asyncio.Lock).acquire"),
                        ("consume", "result(result(asyncio.Lock).acquire).bit_length"),
                    ],
                    "reviewed_helper_uncalled_helper": [("entry", "asyncio.Lock")],
                }
                passed = usage_context_counter == Counter(
                    ("policy/reviewed_helpers.py", context, usage)
                    for context, usage in expected_helper_usages[name]
                )
            elif name.startswith("reviewed_location_"):
                expected_usage = Counter(
                    {("policy/reviewed_transport.py", "asyncio.open_connection"): 1}
                )
                expected_context = Counter(
                    {
                        (
                            "policy/reviewed_transport.py",
                            "Transport.send_once",
                            "asyncio.open_connection",
                        ): 1
                    }
                )
                context_equal = usage_context_counter == expected_context
                passed = usage_counter == expected_usage and context_equal == (
                    name == "reviewed_location_baseline"
                )
            elif name.startswith("sandbox_location_"):
                baseline_qualname = "SandboxHTTPSTransport.send_once"
                expected_usage_contexts = {
                    ("policy/reviewed_transport.py", baseline_qualname, usage): 1
                    for usage in (
                        "asyncio.open_connection",
                        "result(asyncio.open_connection)[1].write",
                        "result(asyncio.open_connection)[1].drain",
                    )
                }
                expected_sink_contexts = {
                    (
                        "policy/reviewed_transport.py",
                        baseline_qualname,
                        primitive,
                    ): 1
                    for primitive in ("asyncio.open_connection", "writer.write")
                }
                usage_context_equal = usage_context_counter == Counter(
                    expected_usage_contexts
                )
                sink_context_equal = sink_context_counter == Counter(
                    expected_sink_contexts
                )
                is_baseline = name == "sandbox_location_baseline"
                passed = (
                    usage_context_equal == is_baseline
                    and sink_context_equal == is_baseline
                    and sum(usage_counter.values()) == 3
                    and len(sink_set) == 2
                )
            elif name == "reviewed_asyncio_near_miss":
                expected_usage = Counter(
                    {("policy/reviewed_asyncio.py", "asyncio.Lock"): 1}
                )
                passed = (
                    dependency_set == {"asyncio"}
                    and {capability for _, capability in capability_set} == {"asyncio"}
                    and usage_counter == expected_usage
                )
            elif name == "declared_capability_undeclared_udp_usage":
                passed = (
                    dependency_set == {"asyncio"}
                    and {capability for _, capability in capability_set} == {"asyncio"}
                    and usage_counter
                    != Counter({("policy/reviewed_asyncio.py", "asyncio.Lock"): 1})
                    and any(
                        usage == "asyncio.loop.create_datagram_endpoint"
                        for _, usage in usage_counter
                    )
                    and any(
                        usage
                        == "result(asyncio.loop.create_datagram_endpoint)[0].sendto"
                        for _, usage in usage_counter
                    )
                )
            else:
                passed = dependency_rejected and (
                    "urllib3" in dependency_set
                    and "urllib3" not in DECLARED_REVIEWED_DEPENDENCIES
                    if unknown_dependency
                    else canonical_socket_sink_found and effect_inventories_rejected
                )
            results.append(
                {
                    "name": name,
                    "passed": passed,
                    "dependencies": dependencies,
                    "capabilities": capabilities,
                    "usages": usages,
                    "sinks": sinks,
                    "dependency_set_equality": not dependency_rejected,
                    "effect_inventory_equality": not effect_inventories_rejected,
                    "effect_usage_context_equality": (
                        usage_context_counter == Counter(expected_context)
                        if name.startswith("reviewed_location_")
                        else usage_context_equal
                        if name.startswith("sandbox_location_")
                        else None
                    ),
                    "effect_sink_context_equality": (
                        sink_context_equal
                        if name.startswith("sandbox_location_")
                        else None
                    ),
                    "definition_time_context_equality": (
                        usage_context_counter
                        == Counter(
                            {
                                (
                                    "policy/reviewed_transport.py",
                                    "Transport.send_once",
                                    "socket.create_connection",
                                ): 1
                            }
                        )
                        if name.startswith("definition_time_")
                        else None
                    ),
                    "automatic_package_scan": name == "automatic_new_module",
                }
            )
    results.extend(run_forward_module_binding_regressions())
    results.extend(run_default_parameter_regressions())
    results.extend(run_dynamic_import_result_regressions())
    results.extend(run_namedexpr_dynamic_import_regressions())
    return all(bool(row["passed"]) for row in results), results


def run_forward_module_binding_regressions() -> list[dict[str, object]]:
    """Parse inert fixtures to verify runtime/definition-time environment isolation.

    These strings are never executed. Even capability calls have no network
    arguments; only the scanner's provenance and occurrence evidence is tested.
    """
    fixtures = {
        "late_import": (
            "async def effect():\n    reader, writer = await late_asyncio.open_connection()\n    writer.writelines([])\n    await writer.drain()\n\nimport asyncio as late_asyncio\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_name": (
            "import asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nopener = asyncio.open_connection\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "early_equivalence": (
            "import asyncio\nopener = asyncio.open_connection\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_importfrom": (
            "async def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nfrom asyncio import open_connection as opener\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_dynamic_builtin": (
            "async def effect():\n    reader, writer = await late_asyncio.open_connection()\n    writer.writelines([])\n    await writer.drain()\n\nlate_asyncio = __import__('asyncio')\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_dynamic_importlib": (
            "import importlib\nasync def effect():\n    reader, writer = await late_asyncio.open_connection()\n    writer.writelines([])\n    await writer.drain()\n\nlate_asyncio = importlib.import_module('asyncio')\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_annassign": (
            "import asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nopener: object = asyncio.open_connection\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_namedexpr": (
            "import asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\n(opener := asyncio.open_connection)\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_unpack": (
            "import asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nopener, harmless = asyncio.open_connection, print\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "late_namedexpr_condition": (
            "import asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nif (opener := asyncio.open_connection):\n    pass\n",
            [
                ("effect", "asyncio.open_connection"),
                ("effect", "result(asyncio.open_connection)[1].writelines"),
                ("effect", "result(asyncio.open_connection)[1].drain"),
            ],
        ),
        "default_forward": (
            "async def effect(opener=late_asyncio.open_connection()):\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "default_early": (
            "import asyncio as late_asyncio\nasync def effect(opener=late_asyncio.open_connection()):\n    pass\n",
            [("<module>", "asyncio.open_connection")],
        ),
        "default_reference": (
            "async def effect(opener=late_asyncio.open_connection):\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "annotation_forward": (
            "def effect(value: late_asyncio.Lock()) -> late_asyncio.Lock():\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "decorator_forward": (
            "@late_asyncio.Lock()\ndef effect():\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "class_base_forward": (
            "class Example(late_asyncio.Lock()):\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "class_decorator_forward": (
            "@late_asyncio.Lock()\nclass Example:\n    pass\nimport asyncio as late_asyncio\n",
            [],
        ),
        "method_global": (
            "import asyncio\nclass Example:\n    opener = print\n    async def effect(self):\n        await opener()\nopener = asyncio.open_connection\n",
            [("Example.effect", "asyncio.open_connection")],
        ),
        "method_default_forward": (
            "class Example:\n    async def effect(self, value=late_asyncio.Lock()):\n        await late_asyncio.open_connection()\nimport asyncio as late_asyncio\n",
            [("Example.effect", "asyncio.open_connection")],
        ),
        "nested_lexical": (
            "import asyncio\ndef outer():\n    local = asyncio.Lock\n    def inner():\n        local()\n        opener()\nopener = asyncio.open_connection\n",
            [
                ("outer.inner", "asyncio.Lock"),
                ("outer.inner", "asyncio.open_connection"),
            ],
        ),
        "helper_global": (
            "def leaf():\n    return factory()\ndef entry():\n    lock = leaf()\n    lock.acquire()\nimport asyncio\nfactory = asyncio.Lock\n",
            [("leaf", "asyncio.Lock"), ("entry", "result(asyncio.Lock).acquire")],
        ),
        "prepass_source_order": (
            "opener = late_asyncio.open_connection\nimport asyncio as late_asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n",
            [],
        ),
        "prepass_unbound_family": (
            "opener = asyncio.open_connection\nimport asyncio\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n",
            [],
        ),
        "final_harmless": (
            "import asyncio\nopener = asyncio.open_connection\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n\nopener = print\n",
            [],
        ),
        "module_expression_forward": (
            "late_asyncio.Lock()\nimport asyncio as late_asyncio\n",
            [],
        ),
        "conditional_name_rejected": (
            "import asyncio\nif condition:\n    opener = asyncio.open_connection\nelse:\n    opener = print\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n",
            None,
        ),
        "conditional_alias_rejected": (
            "if condition:\n    import asyncio as late_asyncio\nelse:\n    import json as late_asyncio\nasync def effect():\n    reader, writer = await late_asyncio.open_connection()\n    writer.writelines([])\n    await writer.drain()\n",
            None,
        ),
        "conditional_clear_rejected": (
            "import asyncio\nopener = asyncio.open_connection\nif condition:\n    opener = print\nasync def effect():\n    reader, writer = await opener()\n    writer.writelines([])\n    await writer.drain()\n",
            None,
        ),
        "default_family_forward": (
            "def effect(value=asyncio.Lock()):\n    pass\nimport asyncio\n",
            [],
        ),
        "class_family_forward": (
            "class Example(asyncio.Lock()):\n    pass\nimport asyncio\n",
            [],
        ),
    }
    results: list[dict[str, object]] = []
    observed: dict[str, Counter] = {}
    for name, (source, expected) in fixtures.items():
        tree = ast.parse(source)
        collector = _ModuleBindingCollector("policy/forward_module.py")
        visitor = _EffectVisitor("policy/forward_module.py", frozenset({"leaf"}))
        try:
            collector.visit(tree)
            visitor.visit(tree)
        except _ModuleBindingReviewRequired:
            passed = expected is None
            results.append(
                {
                    "name": "forward_module_" + name,
                    "passed": passed,
                    "requires_review": True,
                }
            )
            continue
        actual = Counter(
            (str(row["enclosing_qualname"]), str(row["usage"]))
            for row in visitor.usages
        )
        observed[name] = actual
        collector_empty = not any(
            (
                collector.dependencies,
                collector.capabilities,
                collector.usages,
                collector.sinks,
            )
        )
        # The normal pass is the sole source of import occurrences.
        direct_imports = sum(
            isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body
        )
        no_duplicate_dependencies = len(visitor.dependencies) == direct_imports + (
            1 if name.startswith("late_dynamic_") else 0
        )
        passed = (
            expected is not None
            and actual == Counter(expected)
            and collector_empty
            and no_duplicate_dependencies
        )
        results.append(
            {
                "name": "forward_module_" + name,
                "passed": passed,
                "usages": visitor.usages,
                "prepass_emits_no_evidence": collector_empty,
                "single_pass_dependency_occurrences": no_duplicate_dependencies,
            }
        )
    equivalent = observed.get("early_equivalence") == observed.get("late_name")
    for row in results:
        if row["name"] == "forward_module_early_equivalence":
            row["passed"] = bool(row["passed"]) and equivalent
            row["early_late_body_equivalence"] = equivalent
    return results


def run_default_parameter_regressions() -> list[dict[str, object]]:
    """Scan inert AST fixtures only; no fixture code or external calls execute."""
    effect = "asyncio.open_connection"
    downstream = [
        effect,
        f"result({effect})[1].writelines",
        f"result({effect})[1].drain",
    ]
    fixtures = {
        "positional_effect": (
            "import asyncio\nasync def effect(open_fn=asyncio.open_connection):\n    await open_fn()\n",
            [("effect", effect)],
        ),
        "positional_harmless": (
            "async def effect(open_fn=print):\n    open_fn()\n",
            [],
        ),
        "kwonly_effect": (
            "import asyncio\nasync def effect(*, open_fn=asyncio.open_connection):\n    await open_fn()\n",
            [("effect", effect)],
        ),
        "early_binding": (
            "import asyncio as early\nasync def effect(open_fn=early.open_connection):\n    await open_fn()\n",
            [("effect", effect)],
        ),
        "forward_binding_unavailable": (
            "async def effect(open_fn=late.open_connection):\n    await open_fn()\nimport asyncio as late\n",
            [],
        ),
        "result_provenance": (
            "import asyncio\nasync def effect(open_fn=asyncio.open_connection):\n    reader, writer = await open_fn()\n    writer.writelines([])\n    await writer.drain()\n",
            [("effect", item) for item in downstream],
        ),
        "object_factory": (
            "import httpx\nasync def effect(client=httpx.AsyncClient()):\n    await client.post()\n",
            [("<module>", "httpx.AsyncClient"), ("effect", "httpx.AsyncClient.post")],
        ),
        "without_default_shadows_outer": (
            "import asyncio\nopen_fn = asyncio.open_connection\nasync def effect(open_fn):\n    await open_fn()\n",
            [],
        ),
        "positional_alignment": (
            "import asyncio\na = b = asyncio.open_connection\ndef effect(a, b, /, c=asyncio.open_connection):\n    a()\n    b()\n    c()\n",
            [("effect", effect)],
        ),
        "required_kwonly_shadow": (
            "import asyncio\nopen_fn = asyncio.open_connection\ndef effect(*, open_fn, harmless=print):\n    open_fn()\n    harmless()\n",
            [],
        ),
        "method_class_default": (
            "import asyncio\nclass Example:\n    factory = asyncio.open_connection\n    async def effect(self, open_fn=factory):\n        await open_fn()\n",
            [("Example.effect", effect)],
        ),
        "variadic_parameter_shadow": (
            "import asyncio\nargs = kwargs = asyncio.open_connection\ndef effect(*args, **kwargs):\n    args()\n    kwargs()\n",
            [],
        ),
        "default_before_annotation_effect": (
            "import asyncio\nopener = asyncio.open_connection\nasync def effect(open_fn: (opener := print) = opener):\n    reader, writer = await open_fn()\n    writer.writelines([])\n    await writer.drain()\n",
            [("effect", item) for item in downstream],
        ),
        "default_before_annotation_reverse_harmless": (
            "import asyncio\nopener = print\nasync def effect(open_fn: (opener := asyncio.open_connection) = opener):\n    open_fn()\n",
            [],
        ),
        "kwonly_default_before_annotation": (
            "import asyncio\nopener = asyncio.open_connection\nasync def effect(*, open_fn: (opener := print) = opener):\n    await open_fn()\n",
            [("effect", effect)],
        ),
        "collector_normal_default_order_equivalence": (
            "import asyncio\nopener = asyncio.open_connection\ndef entry():\n    return helper()\nasync def helper(open_fn: (opener := print) = opener):\n    reader, writer = await open_fn()\n    writer.writelines([])\n    await writer.drain()\n    return writer\n",
            [("helper", item) for item in downstream],
        ),
    }
    results: list[dict[str, object]] = []
    for name, (source, expected) in fixtures.items():
        tree = ast.parse(source)
        visitor = _EffectVisitor(
            "policy/default_parameters.py",
            frozenset({"helper"})
            if name == "collector_normal_default_order_equivalence"
            else frozenset(),
        )
        visitor.visit(tree)
        collector = _ModuleBindingCollector(visitor.relative)
        collector.visit(tree)
        actual = Counter(
            (row["enclosing_qualname"], row["usage"]) for row in visitor.usages
        )
        no_prepass_evidence = not any(
            (
                collector.dependencies,
                collector.capabilities,
                collector.usages,
                collector.sinks,
            )
        )
        passed = actual == Counter(expected) and no_prepass_evidence
        order_case = "before_annotation" in name or name.endswith(
            "default_order_equivalence"
        )
        order_evidence: dict[str, object] = {}
        if order_case:
            definition = next(
                node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
            )
            normal_default = visitor.parameter_defaults[id(definition)][0]["open_fn"]
            collector_default = collector.parameter_defaults[id(definition)][0][
                "open_fn"
            ]
            expected_default = None if not expected else effect
            equivalent = (
                normal_default == collector_default == expected_default
                and visitor.parameter_defaults[id(definition)]
                == collector.parameter_defaults[id(definition)]
            )
            # Annotation writes must affect module state, while the captured
            # default identity remains the value from before that write.
            expected_module = effect if not expected else None
            annotation_applied = (
                visitor.name_frames[0]["opener"]
                == collector.name_frames[0]["opener"]
                == expected_module
            )
            passed = passed and equivalent and annotation_applied
            order_evidence = {
                "captured_default_provenance": normal_default,
                "collector_normal_default_order_equivalence": equivalent,
                "annotation_module_mutation_applied": annotation_applied,
            }
        if not expected:
            passed = passed and not visitor.sinks
        results.append(
            {
                "name": "default_parameter_" + name,
                "passed": passed,
                "usages": visitor.usages,
                "prepass_emits_no_evidence": no_prepass_evidence,
                **order_evidence,
            }
        )
    # Isolate reviewed callsite evidence from the generic definition inventory:
    # the definition may inventory its default path, but an explicit override
    # must not inject that path into this call's return/effect evidence.
    helper_source = "import asyncio\nasync def helper(open_fn=asyncio.open_connection):\n    reader, writer = await open_fn()\n    writer.writelines([])\n    await writer.drain()\n    return writer\n"
    # A caller may precede the helper definition in source order. Its omitted
    # default must come from the state-only definition-time capture, not from
    # the caller's globals or from a later evidence visit to the helper.
    for label, default, expected in (
        ("harmless", "print", []),
        ("effect", "asyncio.open_connection", downstream),
    ):
        source = (
            "import asyncio\ndef entry():\n    return helper()\n"
            + helper_source.replace("import asyncio\n", "").replace(
                "open_fn=asyncio.open_connection", "open_fn=" + default
            )
        )
        visitor = _EffectVisitor("policy/default_parameters.py", frozenset({"helper"}))
        visitor.visit(ast.parse(source))
        actual = Counter(row["usage"] for row in visitor.usages)
        results.append(
            {
                "name": "default_parameter_helper_later_definition_" + label,
                "passed": actual == Counter(expected),
            }
        )
    helper_cases = {
        "helper_explicit_override": (helper_source, "helper(print)", [], (None,)),
        "helper_omitted_uses_default": (
            helper_source,
            "helper()",
            downstream,
            (f"result({effect})[1]",),
        ),
        "helper_keyword_override": (
            helper_source,
            "helper(open_fn=print)",
            [],
            (None,),
        ),
        "helper_kwonly_default": (
            helper_source.replace("helper(open_fn=", "helper(*, open_fn="),
            "helper()",
            downstream,
            (f"result({effect})[1]",),
        ),
        "helper_forward_requires_review": (
            helper_source.replace("import asyncio\n", "") + "import asyncio\n",
            "helper()",
            None,
            None,
        ),
        "helper_forward_explicit_override": (
            helper_source.replace("import asyncio\n", "") + "import asyncio\n",
            "helper(print)",
            [],
            (None,),
        ),
        "helper_missing_required": (
            helper_source.replace("open_fn=asyncio.open_connection", "open_fn"),
            "helper()",
            None,
            None,
        ),
        "helper_harmless_default": (
            helper_source.replace("open_fn=asyncio.open_connection", "open_fn=print"),
            "helper()",
            [],
            (None,),
        ),
    }
    for name, (source, call, expected, expected_return) in helper_cases.items():
        visitor = _EffectVisitor("policy/default_parameters.py", frozenset({"helper"}))
        visitor.visit(ast.parse(source))
        visitor.usages.clear()
        visitor.sinks.clear()
        visitor.call_evidence.clear()
        try:
            returned = visitor._helper_result(ast.parse(call, mode="eval").body)
            actual = Counter(row["usage"] for row in visitor.usages)
            passed = (
                expected is not None
                and actual == Counter(expected)
                and returned == expected_return
            )
            if expected == []:
                passed = passed and not visitor.sinks
        except ValueError:
            passed = expected is None
        results.append(
            {
                "name": "default_parameter_" + name,
                "passed": passed,
                "callsite_usages": visitor.usages,
            }
        )
    return results


def run_dynamic_import_result_regressions() -> list[dict[str, object]]:
    """Parse inert fixtures; check identity, inventory counts and collector parity."""
    effect = "asyncio.open_connection"
    downstream = [
        effect,
        f"result({effect})[1].writelines",
        f"result({effect})[1].drain",
    ]
    body = (
        '    reader, writer = await IMPORT.open_connection("example.com", 443)\n'
        '    writer.writelines([b"effect"])\n    await writer.drain()\n'
    )
    builtin = '__import__("asyncio")'
    importlib = 'importlib.import_module("asyncio")'
    # source, expected usage identities, literal-import dependency count
    fixtures = {
        "builtin_direct_effect": (
            "async def effect():\n" + body.replace("IMPORT", builtin),
            downstream,
            1,
        ),
        "importlib_direct_effect": (
            "import importlib\nasync def effect():\n"
            + body.replace("IMPORT", importlib),
            downstream,
            1,
        ),
        "builtin_json_near_miss": ('__import__("json").dumps({})\n', [], 1),
        "importlib_json_near_miss": (
            'import importlib\nimportlib.import_module("json").dumps({})\n',
            [],
            1,
        ),
        "builtin_assigned_preserved": (
            "module = "
            + builtin
            + "\nasync def effect():\n"
            + body.replace("IMPORT", "module"),
            downstream,
            1,
        ),
        "importlib_assigned_preserved": (
            "import importlib\nmodule = "
            + importlib
            + "\nasync def effect():\n"
            + body.replace("IMPORT", "module"),
            downstream,
            1,
        ),
        "direct_result_provenance": (
            body.replace("IMPORT", builtin).replace("    ", "").replace("await ", ""),
            downstream,
            1,
        ),
        "nonconstant_not_inferred": (
            "import importlib\nname = user_input\n__import__(name).open_connection()\nimportlib.import_module(name).open_connection()\n",
            [],
            0,
        ),
        "default_parameter_composition": (
            "async def effect(open_fn="
            + builtin
            + ".open_connection):\n    await open_fn()\n",
            [effect],
            1,
        ),
        "importlib_alias": (
            "import importlib as il\nasync def effect():\n"
            + body.replace("IMPORT", 'il.import_module("asyncio")'),
            downstream,
            1,
        ),
        "builtin_local_shadow": (
            "async def effect(__import__=print):\n" + body.replace("IMPORT", builtin),
            [],
            0,
        ),
        "importlib_local_shadow": (
            "import importlib\nasync def effect(importlib):\n"
            + body.replace("IMPORT", importlib),
            [],
            0,
        ),
        "unrelated_call_root": (
            'factory().import_module("asyncio").open_connection()\n',
            [],
            0,
        ),
        "unbound_importlib": (
            'importlib.import_module("asyncio").open_connection()\n',
            [],
            1,
        ),
        "helper_default_composition": (
            "def entry():\n    return helper()\nasync def helper(open_fn="
            + builtin
            + ".open_connection):\n    reader, writer = await open_fn()\n    writer.writelines([])\n    await writer.drain()\n    return writer\n",
            downstream,
            1,
        ),
        "importlib_default_composition": (
            "import importlib\nasync def effect(open_fn="
            + importlib
            + ".open_connection):\n    await open_fn()\n",
            [effect],
            1,
        ),
    }
    results: list[dict[str, object]] = []
    for name, (source, expected, dependency_count) in fixtures.items():
        tree = ast.parse(source)
        visitor = _EffectVisitor("policy/dynamic_import.py", frozenset({"helper"}))
        collector = _ModuleBindingCollector("policy/dynamic_import.py")
        visitor.visit(tree)
        collector.visit(tree)
        no_evidence = not any(
            (
                collector.dependencies,
                collector.capabilities,
                collector.usages,
                collector.sinks,
            )
        )
        literal = "json" if "json_near_miss" in name else "asyncio"
        deps = sum(row["dependency"] == literal for row in visitor.dependencies)
        caps = sum(row["capability"] == literal for row in visitor.capabilities)
        usages = Counter(row["usage"] for row in visitor.usages)
        sinks = Counter(row["primitive"] for row in visitor.sinks)
        passed = (
            usages == Counter(expected)
            and sinks == Counter([effect] if expected else [])
            and deps == dependency_count
            and caps == (dependency_count if literal == "asyncio" else 0)
            and no_evidence
        )
        if name == "direct_result_provenance":
            for index, target in enumerate(("reader", "writer")):
                passed = (
                    passed
                    and visitor.name_frames[0].get(target)
                    == collector.name_frames[0].get(target)
                    == f"result({effect})[{index}]"
                )
        if "default_composition" in name or name == "default_parameter_composition":
            passed = (
                passed and visitor.parameter_defaults == collector.parameter_defaults
            )
        results.append(
            {
                "name": "dynamic_import_" + name,
                "passed": passed,
                "usages": visitor.usages,
                "sinks": visitor.sinks,
                "literal_dependency_occurrences": deps,
                "literal_capability_occurrences": caps,
                "prepass_emits_no_evidence": no_evidence,
                "undeclared_effect_usage_detected": bool(expected)
                and usages != Counter(),
            }
        )
    return results


def run_namedexpr_dynamic_import_regressions() -> list[dict[str, object]]:
    """Check inert import composition fixtures without executing any effect."""
    effect = "asyncio.open_connection"
    downstream = [
        effect,
        f"result({effect})[1].writelines",
        f"result({effect})[1].drain",
    ]
    builtin = '__import__("asyncio")'
    imported = 'importlib.import_module("asyncio")'
    body = (
        "reader, writer = ROOT.open_connection()\n"
        "writer.writelines([])\nwriter.drain()\n"
    )
    fixtures = {
        "builtin_immediate_effect": (
            body.replace("ROOT", "(module := " + builtin + ")"),
            downstream,
            "asyncio",
        ),
        "importlib_immediate_effect": (
            "import importlib\n" + body.replace("ROOT", "(module := " + imported + ")"),
            downstream,
            "asyncio",
        ),
        "builtin_json_near_miss": (
            '(module := __import__("json")).dumps({})\n',
            [],
            "json",
        ),
        "importlib_json_near_miss": (
            'import importlib\n(module := importlib.import_module("json")).dumps({})\n',
            [],
            "json",
        ),
        "immediate_later_equivalence": (
            body.replace("ROOT", "(module := " + builtin + ")"),
            downstream,
            "asyncio",
        ),
        "builtin_shadow": (
            '__import__ = print\n(module := __import__("asyncio")).open_connection()\n',
            [],
            None,
        ),
        "nonconstant": (
            "import importlib\n(module := __import__(runtime_name)).open_connection()\n(module := importlib.import_module(runtime_name)).open_connection()\n",
            [],
            None,
        ),
        "importlib_shadow": (
            'import importlib\nimportlib = print\n(module := importlib.import_module("asyncio")).open_connection()\n',
            [],
            None,
        ),
        "unrelated_factory": ("(module := factory()).open_connection()\n", [], None),
        "binding_survives_after_expression": (
            "(module := " + builtin + ").open_connection()\nmodule.open_connection()\n",
            [effect, effect],
            "asyncio",
        ),
        "builtin_parameter_shadow": (
            'async def effect(__import__=print):\n    (module := __import__("asyncio")).open_connection()\n',
            [],
            None,
        ),
        "importlib_parameter_shadow": (
            'import importlib\nasync def effect(importlib):\n    (module := importlib.import_module("asyncio")).open_connection()\n',
            [],
            None,
        ),
    }
    results = []
    for name, (source, expected, module) in fixtures.items():
        visitor = _EffectVisitor("policy/namedexpr_dynamic.py")
        collector = _ModuleBindingCollector("policy/namedexpr_dynamic.py")
        tree = ast.parse(source)
        visitor.visit(tree)
        collector.visit(tree)
        no_evidence = not any(
            (
                collector.dependencies,
                collector.capabilities,
                collector.usages,
                collector.sinks,
            )
        )
        usages = Counter(row["usage"] for row in visitor.usages)
        sinks = Counter(row["primitive"] for row in visitor.sinks)
        deps = (
            sum(row["dependency"] == module for row in visitor.dependencies)
            if module
            else 0
        )
        caps = sum(row["capability"] == "asyncio" for row in visitor.capabilities)
        state_matches = (
            visitor.name_frames[0].get("module")
            == collector.name_frames[0].get("module")
            == module
        )
        passed = (
            usages == Counter(expected)
            and sinks == Counter(x for x in expected if x == effect)
            and no_evidence
            and state_matches
            and deps == (1 if module else 0)
            and caps == (1 if module == "asyncio" else 0)
        )
        if downstream == expected:
            passed = passed and all(
                visitor.name_frames[0].get(target)
                == collector.name_frames[0].get(target)
                == f"result({effect})[{index}]"
                for index, target in enumerate(("reader", "writer"))
            )
        equivalent = True
        if name == "immediate_later_equivalence":
            later = _EffectVisitor("policy/namedexpr_dynamic.py")
            later.visit(
                ast.parse(
                    "(module := " + builtin + ")\n" + body.replace("ROOT", "module")
                )
            )
            equivalent = (
                Counter(row["usage"] for row in later.usages) == usages
                and later.name_frames == visitor.name_frames
            )
            passed = passed and equivalent
        function_body_verified = True
        if name in {"builtin_immediate_effect", "importlib_immediate_effect"}:
            async_source = source.replace(
                "reader, writer = ", "reader, writer = await "
            ).replace("writer.drain()", "await writer.drain()")
            async_source += "await module.open_connection()\n"
            async_source = "async def effect():\n" + "".join(
                "    " + line + "\n" for line in async_source.splitlines()
            )
            function_visitor = _EffectVisitor("policy/namedexpr_dynamic.py")
            function_visitor.visit(ast.parse(async_source))
            function_body_verified = (
                Counter(row["usage"] for row in function_visitor.usages)
                == Counter([*downstream, effect])
                and Counter(row["primitive"] for row in function_visitor.sinks)
                == Counter([effect, effect])
                and sum(
                    row["dependency"] == "asyncio"
                    for row in function_visitor.dependencies
                )
                == 1
                and sum(
                    row["capability"] == "asyncio"
                    for row in function_visitor.capabilities
                )
                == 1
                and "module" not in function_visitor.name_frames[0]
            )
            passed = passed and function_body_verified
        results.append(
            {
                "name": "namedexpr_dynamic_import_" + name,
                "function_body_verified": function_body_verified,
                "passed": passed,
                "usages": visitor.usages,
                "sinks": visitor.sinks,
                "module_binding": visitor.name_frames[0].get("module"),
                "collector_state_matches": state_matches,
                "prepass_emits_no_evidence": no_evidence,
                "literal_dependency_occurrences": deps,
                "literal_capability_occurrences": caps,
                "immediate_later_equivalent": equivalent,
            }
        )
    return results


def run_mandatory_matrix() -> int:
    """Execute every mapped node and retain per-case execution results."""
    if main() != 0:
        return 1
    results: list[dict[str, object]] = []
    passed = True
    positive_cases = {
        "exact outbound representation equality",
        "legitimate ACTION",
        "legitimate COMPENSATION",
    }
    for case_name in MATRIX_CASES:
        node = MATRIX_CASE_TO_PYTEST_NODE[case_name]
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", node],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        status = "PASS" if completed.returncode == 0 else "FAIL"
        passed = passed and completed.returncode == 0
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout)
            sys.stderr.write(completed.stderr)
        negative = case_name not in positive_cases
        results.append(
            {
                "case_name": case_name,
                "pytest_node": node,
                "executed": True,
                "status": status,
                "expected_outcome": (
                    "LEGITIMATE_EFFECT" if not negative else "REJECTED_FAIL_CLOSED"
                ),
                "zero_effect_evidence": (
                    "asserted_by_behavioral_test" if negative else "not_applicable"
                ),
            }
        )
    matrix_payload = {
        "proof_scope": PROOF_SCOPE,
        "executed_case_count": len(results),
        "passed_case_count": sum(row["status"] == "PASS" for row in results),
        "all_mapped_cases_executed": len(results) == len(MATRIX_CASES),
        "cases": results,
    }
    _write("adversarial-matrix.json", matrix_payload)
    report_path = OUTPUT / "proof-report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        matrix_bytes = json.dumps(
            matrix_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        report.update(
            adversarial_matrix_digest=hashlib.sha256(matrix_bytes).hexdigest(),
            adversarial_matrix_executed=len(results) == len(MATRIX_CASES),
            adversarial_matrix_passed=passed,
        )
        inventory_checks = (
            "dependency_set_equality",
            "effect_capability_set_equality",
            "effect_usage_set_equality",
            "effect_usage_occurrence_equality",
            "effect_usage_context_equality",
            "effect_sink_set_equality",
            "effect_sink_context_equality",
            "registry_set_equality",
            "static_inventory_regressions_passed",
            "direct_attribute_provenance_regressions_passed",
            "namedexpr_provenance_regressions_passed",
            "lexical_alias_scope_regressions_passed",
            "lexical_name_provenance_regressions_passed",
            "reviewed_helper_flow_regressions_passed",
            "forward_module_binding_regressions_passed",
            "default_parameter_provenance_regressions_passed",
            "dynamic_import_result_provenance_regressions_passed",
            "namedexpr_dynamic_import_composition_regressions_passed",
        )
        report["result"] = (
            "PASS"
            if all(report.get(check) is True for check in inventory_checks)
            and len(results) == 38
            and sum(row["status"] == "PASS" for row in results) == 38
            else "FAIL"
        )
        _write("proof-report.json", report)
    return 0 if passed and len(results) == len(MATRIX_CASES) else 1


def main() -> int:
    entries = [
        entry
        for entry in load_bind_coverage_registry()
        if entry.proof_scope == PROOF_SCOPE
    ]
    validation = validate_bind_coverage_registry(load_bind_coverage_registry())
    (
        discovered_dependencies,
        discovered_capabilities,
        discovered_usages,
        discovered_sinks,
    ) = _discover_inventories()
    discovered_dependency_set = {
        str(row["dependency"]) for row in discovered_dependencies
    }
    discovered_capability_set = {
        (str(row["path"]), str(row["capability"])) for row in discovered_capabilities
    }
    discovered_sink_set = {
        (str(row["path"]), str(row["primitive"])) for row in discovered_sinks
    }
    discovered_usage_counter = Counter(
        (str(row["path"]), str(row["usage"])) for row in discovered_usages
    )
    discovered_usage_context_counter = Counter(
        (
            str(row["path"]),
            str(row["enclosing_qualname"]),
            str(row["usage"]),
        )
        for row in discovered_usages
    )
    declared_usage_counter = Counter(
        {
            identity: count_and_classification[0]
            for identity, count_and_classification in DECLARED_EFFECT_USAGES.items()
        }
    )
    declared_usage_context_counter = Counter(
        {
            identity: count_and_classification[0]
            for identity, count_and_classification in (
                DECLARED_EFFECT_USAGE_CONTEXTS.items()
            )
        }
    )
    discovered_sink_context_counter = Counter(
        (
            str(row["path"]),
            str(row["enclosing_qualname"]),
            str(row["primitive"]),
        )
        for row in discovered_sinks
    )
    declared_sink_context_counter = Counter(
        {identity: 1 for identity in DECLARED_EFFECT_SINK_CONTEXTS}
    )
    declared_capability_set = set(DECLARED_EFFECT_CAPABILITIES)
    declared_sink_set = set(DECLARED_EFFECT_SINKS)
    declared_dependency_set = set(DECLARED_REVIEWED_DEPENDENCIES)
    regressions_passed, regression_results = run_static_inventory_regressions()
    attribute_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("direct_attribute_")
    ]
    attribute_regressions_passed = len(attribute_regression_results) == 9 and all(
        bool(row["passed"]) for row in attribute_regression_results
    )
    namedexpr_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("namedexpr_")
        and not str(row["name"]).startswith("namedexpr_dynamic_import_")
    ]
    namedexpr_regressions_passed = len(namedexpr_regression_results) == 4 and all(
        bool(row["passed"]) for row in namedexpr_regression_results
    )
    lexical_alias_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("lexical_alias_")
    ]
    lexical_alias_regressions_passed = len(
        lexical_alias_regression_results
    ) == 7 and all(bool(row["passed"]) for row in lexical_alias_regression_results)
    lexical_name_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("lexical_name_")
    ]
    lexical_name_regressions_passed = len(
        lexical_name_regression_results
    ) == 11 and all(bool(row["passed"]) for row in lexical_name_regression_results)
    helper_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("reviewed_helper_")
    ]
    helper_regressions_passed = len(helper_regression_results) == 8 and all(
        bool(row["passed"]) for row in helper_regression_results
    )
    forward_regression_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("forward_module_")
    ]
    forward_regressions_passed = len(forward_regression_results) == 30 and all(
        bool(row["passed"]) for row in forward_regression_results
    )
    default_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("default_parameter_")
    ]
    default_regressions_passed = len(default_results) == 26 and all(
        bool(row["passed"]) for row in default_results
    )
    dynamic_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("dynamic_import_")
    ]
    dynamic_regressions_passed = len(dynamic_results) == 16 and all(
        bool(row["passed"]) for row in dynamic_results
    )
    composition_results = [
        row
        for row in regression_results
        if str(row["name"]).startswith("namedexpr_dynamic_import_")
    ]
    composition_regressions_passed = len(composition_results) == 12 and all(
        bool(row["passed"]) for row in composition_results
    )
    registered_boundaries = {
        (entry.effect_boundary_id, entry.dispatch_kind) for entry in entries
    }
    expected_boundaries = {
        ("registered-webhook-action", "ACTION"),
        ("registered-webhook-compensation", "COMPENSATION"),
        ("native-v2-sandbox-action", "ACTION"),
    }
    passed = (
        validation.valid
        and discovered_dependency_set == declared_dependency_set
        and discovered_capability_set == declared_capability_set
        and discovered_usage_counter == declared_usage_counter
        and discovered_usage_context_counter == declared_usage_context_counter
        and discovered_sink_set == declared_sink_set
        and discovered_sink_context_counter == declared_sink_context_counter
        and regressions_passed
        and attribute_regressions_passed
        and namedexpr_regressions_passed
        and lexical_alias_regressions_passed
        and lexical_name_regressions_passed
        and helper_regressions_passed
        and forward_regressions_passed
        and default_regressions_passed
        and dynamic_regressions_passed
        and composition_regressions_passed
        and registered_boundaries == expected_boundaries
        and len(entries) == 3
    )
    registry_payload = [entry.__dict__ for entry in entries]
    registry_bytes = json.dumps(
        registry_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    tested_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    provenance = {
        "proof_scope": PROOF_SCOPE,
        "tested_sha": tested_sha,
        "source_sha": os.environ.get("GITHUB_SHA", tested_sha),
        "registry_digest": hashlib.sha256(registry_bytes).hexdigest(),
        "architecture_status": "FROZEN",
        "implementation_status": "IMPLEMENTED",
        "proof_status": "NOT_PROVEN",
    }
    effect_sink_inventory = [
        {
            **row,
            "classification": DECLARED_EFFECT_SINKS.get(
                (str(row["path"]), str(row["primitive"])), "UNDECLARED"
            ),
            "context_classification": DECLARED_EFFECT_SINK_CONTEXTS.get(
                (
                    str(row["path"]),
                    str(row["enclosing_qualname"]),
                    str(row["primitive"]),
                ),
                "UNDECLARED",
            ),
        }
        for row in discovered_sinks
    ]
    effect_capability_inventory = [
        {
            **row,
            "classification": DECLARED_EFFECT_CAPABILITIES.get(
                (str(row["path"]), str(row["capability"])), "UNDECLARED"
            ),
        }
        for row in discovered_capabilities
    ]
    seen_usages: Counter[tuple[str, str, str]] = Counter()
    effect_usage_inventory = []
    for row in discovered_usages:
        context_identity = (
            str(row["path"]),
            str(row["enclosing_qualname"]),
            str(row["usage"]),
        )
        seen_usages[context_identity] += 1
        declaration = DECLARED_EFFECT_USAGE_CONTEXTS.get(context_identity)
        effect_usage_inventory.append(
            {
                **row,
                "occurrence": seen_usages[context_identity],
                "classification": (
                    declaration[1]
                    if declaration is not None
                    and seen_usages[context_identity] <= declaration[0]
                    else "UNDECLARED"
                ),
            }
        )
    reviewed_dependency_inventory = [
        {
            **row,
            "classification": DECLARED_REVIEWED_DEPENDENCIES.get(
                str(row["dependency"]), "UNDECLARED"
            ),
        }
        for row in discovered_dependencies
    ]
    # Retain the historical artifact name while making the separate sink
    # inventory explicit for this closure.
    _write("execution-boundary-inventory.json", effect_sink_inventory)
    _write("effect-capability-inventory.json", effect_capability_inventory)
    _write("effect-usage-inventory.json", effect_usage_inventory)
    _write("effect-usage-context-inventory.json", effect_usage_inventory)
    _write("effect-sink-inventory.json", effect_sink_inventory)
    _write("effect-sink-context-inventory.json", effect_sink_inventory)
    _write("reviewed-dependency-inventory.json", reviewed_dependency_inventory)
    _write(
        "static-inventory-regressions.json",
        {
            "passed": regressions_passed,
            "direct_attribute_provenance_regressions_passed": (
                attribute_regressions_passed
            ),
            "namedexpr_provenance_regressions_passed": (namedexpr_regressions_passed),
            "lexical_alias_scope_regressions_passed": (
                lexical_alias_regressions_passed
            ),
            "lexical_name_provenance_regressions_passed": (
                lexical_name_regressions_passed
            ),
            "reviewed_helper_flow_regressions_passed": helper_regressions_passed,
            "forward_module_binding_regressions_passed": forward_regressions_passed,
            "default_parameter_provenance_regressions_passed": default_regressions_passed,
            "dynamic_import_result_provenance_regressions_passed": dynamic_regressions_passed,
            "namedexpr_dynamic_import_composition_regressions_passed": composition_regressions_passed,
            "case_count": len(regression_results),
            "cases": regression_results,
            "limitation": (
                "bounded lexical alias/Name and intraprocedural AST analysis; direct "
                "Import/ImportFrom and constant-string dynamic-import aliases, "
                "separate source-order initialization and completed direct module bindings, "
                "reviewed same-module direct helper argument/return flow, "
                "assignment, NamedExpr, Await, simple "
                "tuple/list unpacking, and direct invocation on known capability "
                "provenance are in scope; reflection, monkeypatching, arbitrary "
                "data-dependent or interprocedural dispatch, and interpreter/native "
                "compromise are out of scope"
            ),
        },
    )
    _write("bind-coverage-registry.json", registry_payload)
    if set(MATRIX_CASE_TO_PYTEST_NODE) != set(MATRIX_CASES):
        raise RuntimeError("mandatory matrix mapping is incomplete")
    if len(set(MATRIX_CASE_TO_PYTEST_NODE.values())) != len(MATRIX_CASES):
        raise RuntimeError("mandatory matrix nodes must be unique")
    _write(
        "adversarial-matrix.json",
        {
            "cases": [
                {
                    "name": name,
                    "required": True,
                    "pytest_node": MATRIX_CASE_TO_PYTEST_NODE[name],
                }
                for name in MATRIX_CASES
            ],
            "result_source": "each pytest node performs the named behavior",
        },
    )
    _write(
        "near-miss.json",
        {
            "undeclared_capabilities": sorted(
                discovered_capability_set - declared_capability_set
            ),
            "missing_declared_capabilities": sorted(
                declared_capability_set - discovered_capability_set
            ),
            "undeclared_sinks": sorted(discovered_sink_set - declared_sink_set),
            "missing_declared_sinks": sorted(declared_sink_set - discovered_sink_set),
            "undeclared_sink_contexts": sorted(
                (identity, count)
                for identity, count in (
                    discovered_sink_context_counter - declared_sink_context_counter
                ).items()
            ),
            "missing_declared_sink_contexts": sorted(
                (identity, count)
                for identity, count in (
                    declared_sink_context_counter - discovered_sink_context_counter
                ).items()
            ),
            "undeclared_usage_occurrences": sorted(
                (path, usage, count)
                for (path, usage), count in (
                    discovered_usage_counter - declared_usage_counter
                ).items()
            ),
            "missing_declared_usage_occurrences": sorted(
                (path, usage, count)
                for (path, usage), count in (
                    declared_usage_counter - discovered_usage_counter
                ).items()
            ),
            "undeclared_usage_context_occurrences": sorted(
                (identity, count)
                for identity, count in (
                    discovered_usage_context_counter - declared_usage_context_counter
                ).items()
            ),
            "missing_declared_usage_context_occurrences": sorted(
                (identity, count)
                for identity, count in (
                    declared_usage_context_counter - discovered_usage_context_counter
                ).items()
            ),
            "undeclared_dependencies": sorted(
                discovered_dependency_set - declared_dependency_set
            ),
            "missing_declared_dependencies": sorted(
                declared_dependency_set - discovered_dependency_set
            ),
        },
    )
    _write(
        "immutable-dispatch-evidence.json",
        {"representation": "ImmutableFinalDispatch", "proof_status": "NOT_PROVEN"},
    )
    _write(
        "compensation-authority-evidence.json",
        {"authority": "CompensationEligibilityGrant", "proof_status": "NOT_PROVEN"},
    )
    _write("provenance.json", provenance)
    _write(
        "proof-report.json",
        {
            **provenance,
            "dependency_set_equality": (
                discovered_dependency_set == declared_dependency_set
            ),
            "inventory_set_equality": discovered_sink_set == declared_sink_set,
            "effect_capability_set_equality": (
                discovered_capability_set == declared_capability_set
            ),
            "effect_usage_set_equality": (
                set(discovered_usage_counter) == set(declared_usage_counter)
            ),
            "effect_usage_occurrence_equality": (
                discovered_usage_counter == declared_usage_counter
            ),
            "effect_usage_context_equality": (
                discovered_usage_context_counter == declared_usage_context_counter
            ),
            "effect_sink_set_equality": discovered_sink_set == declared_sink_set,
            "effect_sink_context_equality": (
                discovered_sink_context_counter == declared_sink_context_counter
            ),
            "static_inventory_regressions_passed": regressions_passed,
            "direct_attribute_provenance_regressions_passed": (
                attribute_regressions_passed
            ),
            "namedexpr_provenance_regressions_passed": (namedexpr_regressions_passed),
            "lexical_alias_scope_regressions_passed": (
                lexical_alias_regressions_passed
            ),
            "lexical_name_provenance_regressions_passed": (
                lexical_name_regressions_passed
            ),
            "reviewed_helper_flow_regressions_passed": helper_regressions_passed,
            "forward_module_binding_regressions_passed": forward_regressions_passed,
            "default_parameter_provenance_regressions_passed": default_regressions_passed,
            "dynamic_import_result_provenance_regressions_passed": dynamic_regressions_passed,
            "namedexpr_dynamic_import_composition_regressions_passed": composition_regressions_passed,
            "registry_set_equality": registered_boundaries == expected_boundaries,
            "result": "PENDING_MATRIX" if passed else "FAIL",
            "explicit_non_claims": [
                "all VERITAS external I/O is Bind-governed",
                "arbitrary equivalent-privilege in-process compromise resistance",
                "TLS/provider identity proof",
                "universal exactly-once external delivery",
                "production readiness",
            ],
            "bounded_analysis_limitations": [
                "reflection not statically resolvable",
                "arbitrary data-dependent dispatch",
                "monkeypatching",
                "arbitrary interprocedural provenance",
                "full Python compiler symbol-table or closure equivalence",
                "function-body globals before normal module initialization completes",
                "arbitrary module control-flow execution",
                "interpreter or native compromise",
            ],
        },
    )
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-matrix", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run_mandatory_matrix() if arguments.run_matrix else main())
