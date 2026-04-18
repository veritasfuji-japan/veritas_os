"""Unit tests for observability metric recording helpers."""
from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth as auth_module
from veritas_os.api import routes_memory
from veritas_os.api import server
from veritas_os.audit import trustlog_signed
from veritas_os.logging import trust_log


@pytest.fixture(autouse=True)
def _restore_server_pipeline_state():
    """Restore global lazy pipeline state after each test in this module."""
    original = server._pipeline_state
    try:
        yield
    finally:
        server._pipeline_state = original


class _MetricProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def labels(self, **labels: Any) -> "_MetricProbe":
        self.calls.append({"labels": labels})
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append({"inc": amount})

    def observe(self, value: float) -> None:
        self.calls.append({"observe": value})

    def set(self, value: float) -> None:
        self.calls.append({"set": value})


def test_record_decide_and_gauge_helpers(monkeypatch):
    metrics = importlib.import_module("veritas_os.observability.metrics")
    decide_total = _MetricProbe()
    decide_duration = _MetricProbe()
    telos = _MetricProbe()
    degraded = _MetricProbe()

    monkeypatch.setattr(metrics, "VERITAS_DECIDE_TOTAL", decide_total)
    monkeypatch.setattr(metrics, "VERITAS_DECIDE_DURATION_SECONDS", decide_duration)
    monkeypatch.setattr(metrics, "VERITAS_TELOS_SCORE", telos)
    monkeypatch.setattr(metrics, "VERITAS_DEGRADED_SUBSYSTEMS", degraded)

    metrics.record_decide(status="allow", mode="fast", intent="qa", duration_seconds=0.25)
    metrics.set_telos_score(user_id="u-1", score=0.87)
    metrics.set_degraded_subsystems(2)

    assert any(call.get("labels") == {"status": "allow", "mode": "fast", "intent": "qa"} for call in decide_total.calls)
    assert any(call.get("observe") == 0.25 for call in decide_duration.calls)
    assert any(call.get("labels") == {"user_id": "u-1"} for call in telos.calls)
    assert any(call.get("set") == 2.0 for call in degraded.calls)


def test_fuji_and_memory_metrics(monkeypatch):
    metrics = importlib.import_module("veritas_os.observability.metrics")
    fuji_decisions = _MetricProbe()
    fuji_violations = _MetricProbe()
    mem_ops = _MetricProbe()

    monkeypatch.setattr(metrics, "VERITAS_FUJI_DECISIONS_TOTAL", fuji_decisions)
    monkeypatch.setattr(metrics, "VERITAS_FUJI_VIOLATIONS_TOTAL", fuji_violations)
    monkeypatch.setattr(metrics, "VERITAS_MEMORY_OPERATIONS_TOTAL", mem_ops)

    metrics.record_fuji_decision("deny")
    metrics.record_fuji_violations(["pii", "policy"])
    metrics.record_memory_operation("search", "semantic")

    assert any(call.get("labels") == {"decision_status": "deny"} for call in fuji_decisions.calls)
    assert any(call.get("labels") == {"violation_type": "pii"} for call in fuji_violations.calls)
    assert any(call.get("labels") == {"operation": "search", "kind": "semantic"} for call in mem_ops.calls)


def test_required_evidence_telemetry_metrics(monkeypatch):
    """Required-evidence hardening counters should emit domain/template labels."""
    metrics = importlib.import_module("veritas_os.observability.metrics")
    unknown_total = _MetricProbe()
    alias_total = _MetricProbe()
    profile_miss_total = _MetricProbe()

    monkeypatch.setattr(metrics, "UNKNOWN_REQUIRED_EVIDENCE_KEY_TOTAL", unknown_total)
    monkeypatch.setattr(
        metrics,
        "REQUIRED_EVIDENCE_ALIAS_NORMALIZED_TOTAL",
        alias_total,
    )
    monkeypatch.setattr(
        metrics,
        "REQUIRED_EVIDENCE_PROFILE_MISS_TOTAL",
        profile_miss_total,
    )

    metrics.record_required_evidence_telemetry(
        domain="aml_kyc",
        template_id="tmpl-1",
        source="financial_poc_pack",
        mode="strict",
        unknown_key_total=2,
        alias_normalized_total=3,
        profile_miss_total=1,
    )

    expected_labels = {
        "domain": "aml_kyc",
        "template_id": "tmpl-1",
        "source": "financial_poc_pack",
        "mode": "strict",
    }
    assert any(call.get("labels") == expected_labels for call in unknown_total.calls)
    assert any(call.get("inc") == 2.0 for call in unknown_total.calls)
    assert any(call.get("labels") == expected_labels for call in alias_total.calls)
    assert any(call.get("inc") == 3.0 for call in alias_total.calls)
    assert any(call.get("labels") == expected_labels for call in profile_miss_total.calls)
    assert any(call.get("inc") == 1.0 for call in profile_miss_total.calls)


def test_noop_mode_without_prometheus_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    metrics = importlib.reload(importlib.import_module("veritas_os.observability.metrics"))

    # Must not raise even when prometheus_client is missing.
    metrics.record_decide(status="allow", mode="normal", intent="unknown", duration_seconds=0.01)
    metrics.record_auth_rejection("api_key_invalid")
    metrics.observe_pipeline_stage_duration("kernel_execute", 0.05)


def test_decide_unavailable_resets_stale_pipeline_state(monkeypatch):
    """Unavailable decide path should reset stale lazy state for next requests."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    auth_module._log_api_key_source_once.cache_clear()
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="boom", attempted=True),
    )
    client = TestClient(server.app)

    response = client.post(
        "/v1/decide",
        headers={"X-API-Key": "test-key"},
        json={"query": "reset check"},
    )

    assert response.status_code == 503
    assert server._pipeline_state.err is None
    assert server._pipeline_state.attempted is False


def test_health_recovers_pipeline_boom_sentinel(monkeypatch):
    """Health endpoint should recover from the temporary pipeline boom sentinel."""
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="boom", attempted=True),
    )
    client = TestClient(server.app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["pipeline"] == "ok"


def test_health_keeps_forced_pipeline_unavailable(monkeypatch):
    """Health endpoint must preserve explicit forced-unavailable pipeline states."""
    monkeypatch.setattr(
        server,
        "_pipeline_state",
        server._LazyState(obj=None, err="forced", attempted=True),
    )
    client = TestClient(server.app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["pipeline"] == "unavailable"


def test_memory_entry_observer_uses_count_only(monkeypatch):
    """Memory entry gauge observer must not trigger extra search calls."""
    called = {"count": 0, "search": 0}

    class _Store:
        @staticmethod
        def search(**_: Any):
            called["search"] += 1
            return []

    monkeypatch.setattr(
        routes_memory,
        "set_memory_store_entries",
        lambda user_id, entries: None,
    )
    routes_memory._observe_memory_store_entries(_Store(), "u-1")

    assert called["count"] == 0
    assert called["search"] == 0


def test_trustlog_metric_helpers_emit_labels(monkeypatch):
    metrics = importlib.import_module("veritas_os.observability.metrics")
    append_ok = _MetricProbe()
    append_fail = _MetricProbe()
    sign_fail = _MetricProbe()
    mirror_fail = _MetricProbe()
    anchor_fail = _MetricProbe()
    verify_fail = _MetricProbe()
    last_success = _MetricProbe()

    monkeypatch.setattr(metrics, "TRUSTLOG_APPEND_SUCCESS_TOTAL", append_ok)
    monkeypatch.setattr(metrics, "TRUSTLOG_APPEND_FAILURE_TOTAL", append_fail)
    monkeypatch.setattr(metrics, "TRUSTLOG_SIGN_FAILURE_TOTAL", sign_fail)
    monkeypatch.setattr(metrics, "TRUSTLOG_MIRROR_FAILURE_TOTAL", mirror_fail)
    monkeypatch.setattr(metrics, "TRUSTLOG_ANCHOR_FAILURE_TOTAL", anchor_fail)
    monkeypatch.setattr(metrics, "TRUSTLOG_VERIFY_FAILURE_TOTAL", verify_fail)
    monkeypatch.setattr(metrics, "TRUSTLOG_LAST_SUCCESS_TIMESTAMP", last_success)
    monkeypatch.setattr(metrics, "_posture_label", lambda: "dev")
    monkeypatch.setattr(metrics, "_now_unix_timestamp", lambda: 1700000000.0)

    metrics.record_trustlog_append_success()
    metrics.record_trustlog_append_failure("write_error")
    metrics.record_trustlog_sign_failure("file", "bad_key")
    metrics.record_trustlog_mirror_failure("s3_object_lock", "denied")
    metrics.record_trustlog_anchor_failure("local", "io_error")
    metrics.record_trustlog_verify_failure("witness", "chain_broken")

    assert any(call.get("labels") == {"posture": "dev"} for call in append_ok.calls)
    assert any(call.get("set") == 1700000000.0 for call in last_success.calls)
    assert any(
        call.get("labels") == {"posture": "dev", "reason": "write_error"}
        for call in append_fail.calls
    )
    assert any(
        call.get("labels") == {"signer_backend": "file", "reason": "bad_key"}
        for call in sign_fail.calls
    )
    assert any(
        call.get("labels") == {"backend": "s3_object_lock", "reason": "denied"}
        for call in mirror_fail.calls
    )
    assert any(
        call.get("labels") == {"backend": "local", "reason": "io_error"}
        for call in anchor_fail.calls
    )
    assert any(
        call.get("labels") == {"ledger": "witness", "reason": "chain_broken"}
        for call in verify_fail.calls
    )


def test_trustlog_signed_emits_sign_and_mirror_failure_metrics(monkeypatch):
    class _FailingSigner:
        signer_type = "file"

        @staticmethod
        def signer_key_id() -> str:
            return "test"

        @staticmethod
        def sign_payload_hash(_: str) -> str:
            raise ValueError("bad-sign")

    recorded: dict[str, list[tuple[str, str]]] = {"sign": [], "mirror": []}
    monkeypatch.setattr(trustlog_signed, "_resolve_signer", lambda **_: _FailingSigner())
    monkeypatch.setattr(trustlog_signed, "_read_last_entry", lambda *_: None)
    monkeypatch.setattr(trustlog_signed, "record_trustlog_sign_failure", lambda backend, reason: recorded["sign"].append((backend, str(reason))))
    monkeypatch.setattr(trustlog_signed, "observe_trustlog_sign_latency", lambda *_: None)
    monkeypatch.setattr(trustlog_signed, "record_trustlog_mirror_failure", lambda backend, reason: recorded["mirror"].append((str(backend), str(reason))))

    with pytest.raises(trustlog_signed.SignedTrustLogWriteError):
        trustlog_signed.append_signed_decision({"request_id": "r-1"})

    assert recorded["sign"]
    assert recorded["sign"][0][0] == "file"

    monkeypatch.setattr(trustlog_signed, "build_storage_mirror", lambda **_: (_ for _ in ()).throw(ValueError("invalid")))
    trustlog_signed._mirror_to_worm("line\n")
    assert recorded["mirror"]
    assert recorded["mirror"][0][0] == "invalid"


def test_verify_failure_metric_emitted(monkeypatch):
    emitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        trust_log,
        "record_trustlog_verify_failure",
        lambda ledger, reason: emitted.append((ledger, str(reason))),
    )
    monkeypatch.setattr(
        trust_log,
        "verify_full_ledger",
        lambda **_: {"ok": False, "total_entries": 1, "valid_entries": 0, "invalid_entries": 1, "chain_ok": False, "signature_ok": True, "linkage_ok": True, "mirror_ok": True, "last_hash": None, "detailed_errors": [{"reason": "sha256_mismatch", "index": 0, "code": "tamper_suspected"}]},
    )

    result = trust_log.verify_trust_log()

    assert result["ok"] is False
    assert ("full", "verification_failed") in emitted
