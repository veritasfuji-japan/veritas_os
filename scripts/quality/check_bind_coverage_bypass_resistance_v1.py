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
    """Resolve effect-family imports, aliases, and simple client instances."""

    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.context_stack: list[str] = []
        self.aliases: dict[str, str] = {}
        self.instances: dict[str, str] = {}
        self.attribute_instances: dict[tuple[str, str], str] = {}
        self.dependencies: list[dict[str, object]] = []
        self.capabilities: list[dict[str, object]] = []
        self.usages: list[dict[str, object]] = []
        self.sinks: list[dict[str, object]] = []

    def _current_qualname(self) -> str:
        return ".".join(self.context_stack) if self.context_stack else "<module>"

    def _visit_body_context(self, body: list[ast.stmt], name: str) -> None:
        self.context_stack.append(name)
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self.context_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._visit_body_context(node.body, node.name)

    def _visit_function_definition(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        self._visit_body_context(node.body, node.name)

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
            self.aliases[local] = (
                imported.name if imported.asname else imported.name.split(".", 1)[0]
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
            self.aliases[imported.asname or imported.name] = identity
            if _is_capability_import(identity):
                self._add_capability(identity, node.lineno)

    @staticmethod
    def _unwrap_await(value: ast.AST) -> ast.AST:
        return value.value if isinstance(value, ast.Await) else value

    def _resolve_name(self, node: ast.AST) -> str:
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
        canonical = _canonical_name(raw, self.aliases)
        head, separator, tail = canonical.partition(".")
        if head in self.instances:
            return self.instances[head] + (separator + tail if separator else "")
        return canonical

    def _value_provenance(self, value: ast.AST) -> str | None:
        value = self._unwrap_await(value)
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
            self.instances[target.id] = provenance
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
            self.instances.pop(target.id, None)
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
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            return
        canonical = _canonical_name(_expression_name(value.func), self.aliases)
        if canonical not in {"__import__", "importlib.import_module"} or not value.args:
            return
        argument = value.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            if _is_capability_import(argument.value):
                self.aliases[target.id] = argument.value

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
        raw = _expression_name(node.func)
        canonical = self._resolve_name(node.func)
        if canonical in {"__import__", "importlib.import_module"} and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                self._add_dependency(argument.value, node.lineno)
                if _is_capability_import(argument.value):
                    self._add_capability(argument.value, node.lineno)
        if self._has_effect_provenance(canonical):
            self.usages.append(
                {
                    "path": self.relative,
                    "enclosing_qualname": self._current_qualname(),
                    "usage": canonical,
                    "line": node.lineno,
                }
            )
        if _is_effect_sink(canonical) or raw in _PRESERVED_SINKS:
            self.sinks.append(
                {
                    "path": self.relative,
                    "enclosing_qualname": self._current_qualname(),
                    "primitive": raw if raw in _PRESERVED_SINKS else canonical,
                    "line": node.lineno,
                }
            )
        self.generic_visit(node)


def _discover_inventories(
    root: Path = POLICY_ROOT,
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
        visitor = _EffectVisitor(relative)
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
            "if (label := 'network'):\n"
            "    pass\n",
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
                policy_root
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
                    and {capability for _, capability in capability_set}
                    == {"asyncio"}
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
    return all(bool(row["passed"]) for row in results), results


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
    ]
    namedexpr_regressions_passed = len(namedexpr_regression_results) == 4 and all(
        bool(row["passed"]) for row in namedexpr_regression_results
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
            "namedexpr_provenance_regressions_passed": (
                namedexpr_regressions_passed
            ),
            "case_count": len(regression_results),
            "cases": regression_results,
            "limitation": (
                "bounded intraprocedural AST analysis; assignment, NamedExpr, "
                "Await, simple "
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
            "namedexpr_provenance_regressions_passed": (
                namedexpr_regressions_passed
            ),
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
