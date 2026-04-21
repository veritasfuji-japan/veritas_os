"""Tests for bind-controlled policy bundle promotion integration path."""

from __future__ import annotations

import hashlib
import json

import pytest

from veritas_os.logging.encryption import generate_key
from veritas_os.policy import find_bind_receipts
from veritas_os.policy.bind_artifacts import FinalOutcome
from veritas_os.policy.policy_bundle_promotion import promote_policy_bundle_with_bind_boundary


def _write_bundle(bundle_dir, *, with_signature: bool = True) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "compiled").mkdir(parents=True, exist_ok=True)

    canonical_ir = {
        "policy_id": "policy.operations",
        "version": "1.0.0",
        "title": "Ops Policy",
        "description": "Operations policy for testing",
        "effective_date": "2026-04-20",
        "scope": {
            "domains": ["operations"],
            "routes": ["/v1/decide"],
            "actors": ["operator"],
        },
        "conditions": [],
        "constraints": [],
        "requirements": {},
        "outcome": {"default_action": "allow"},
        "obligations": [],
        "test_vectors": [],
        "metadata": {},
        "source_refs": [],
    }
    (bundle_dir / "compiled" / "canonical_ir.json").write_text(
        json.dumps(canonical_ir, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "0.1",
        "policy_id": "policy.operations",
        "version": "1.0.0",
        "semantic_hash": "dummy-semantic-hash",
        "compiler_version": "test",
        "compiled_at": "2026-04-20T00:00:00Z",
        "signing": {"algorithm": "sha256"},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    (bundle_dir / "manifest.json").write_bytes(manifest_bytes)

    if with_signature:
        (bundle_dir / "manifest.sig").write_text(
            hashlib.sha256(manifest_bytes).hexdigest(),
            encoding="utf-8",
        )


def _base_kwargs(tmp_path):
    bundles_root = tmp_path / "bundles"
    old_bundle = bundles_root / "bundle-v1"
    new_bundle = bundles_root / "bundle-v2"
    _write_bundle(old_bundle, with_signature=True)
    _write_bundle(new_bundle, with_signature=True)

    pointer_path = tmp_path / "runtime" / "active_bundle.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(
            {
                "active_bundle_dir": str(old_bundle.resolve()),
                "decision_id": "dec-old",
                "execution_intent_id": "ei-old",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "decision_id": "dec-policy-bundle",
        "request_id": "req-policy-bundle",
        "actor_identity": "governance-operator",
        "policy_snapshot_id": "policy-snapshot-1",
        "decision_hash": "b" * 64,
        "target_bundle_dir": new_bundle,
        "pointer_path": pointer_path,
        "allowed_root": bundles_root,
        "decision_ts": "2026-04-20T12:00:00Z",
        "execution_intent_id": "ei-policy-bundle",
    }


def test_policy_bundle_promotion_success_commit(tmp_path) -> None:
    kwargs = _base_kwargs(tmp_path)

    receipt = promote_policy_bundle_with_bind_boundary(
        **kwargs,
        bind_ts="2026-04-20T12:00:10Z",
        bind_receipt_id="br-promotion-success",
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    stored = json.loads(kwargs["pointer_path"].read_text(encoding="utf-8"))
    assert stored["active_bundle_dir"] == str(kwargs["target_bundle_dir"].resolve())


def test_policy_bundle_promotion_blocked_bind(tmp_path) -> None:
    kwargs = _base_kwargs(tmp_path)

    receipt = promote_policy_bundle_with_bind_boundary(
        **kwargs,
        approval_context={"policy_bundle_promotion_approved": False},
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED


def test_policy_bundle_promotion_apply_failure(tmp_path, monkeypatch) -> None:
    kwargs = _base_kwargs(tmp_path)

    def _raise_oserror(*args, **kwds):
        del args, kwds
        raise OSError("disk full")

    monkeypatch.setattr(
        "veritas_os.policy.bind_boundary_adapters.atomic_write_json",
        _raise_oserror,
    )

    receipt = promote_policy_bundle_with_bind_boundary(**kwargs, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.APPLY_FAILED
    assert "BIND_APPLY_FAILED" in (receipt.rollback_reason or "")


def test_policy_bundle_promotion_postcondition_failure_rolls_back(tmp_path) -> None:
    kwargs = _base_kwargs(tmp_path)
    (kwargs["target_bundle_dir"] / "manifest.sig").unlink(missing_ok=True)

    receipt = promote_policy_bundle_with_bind_boundary(
        **kwargs,
        require_signature=True,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    restored = json.loads(kwargs["pointer_path"].read_text(encoding="utf-8"))
    assert restored["active_bundle_dir"].endswith("bundle-v1")


def test_policy_bundle_promotion_lineage_and_trustlog_linkage(tmp_path, monkeypatch) -> None:
    from veritas_os.logging import trust_log

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)
    monkeypatch.setattr(trust_log, "_append_stats", {"success": 0, "failure": 0}, raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)

    kwargs = _base_kwargs(tmp_path)
    receipt = promote_policy_bundle_with_bind_boundary(**kwargs, append_trustlog=True)

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert receipt.execution_intent_id == kwargs["execution_intent_id"]
    assert receipt.decision_id == kwargs["decision_id"]
    assert receipt.trustlog_hash

    by_decision = find_bind_receipts(decision_id=kwargs["decision_id"])
    by_intent = find_bind_receipts(execution_intent_id=kwargs["execution_intent_id"])
    by_receipt = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)
    assert len(by_decision) == 1
    assert len(by_intent) == 1
    assert len(by_receipt) == 1


def test_policy_bundle_promotion_preserves_bind_policy_overrides(tmp_path) -> None:
    kwargs = _base_kwargs(tmp_path)

    receipt = promote_policy_bundle_with_bind_boundary(
        **kwargs,
        approval_context={
            "policy_bundle_promotion_approved": True,
            "bind_adjudication": {"drift_required": False},
        },
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED


def test_policy_bundle_promotion_backward_compatible_with_existing_execute_call(tmp_path) -> None:
    from veritas_os.policy.bind_execution import ReferenceBindAdapter, execute_bind_boundary
    from veritas_os.policy.bind_artifacts import ExecutionIntent

    adapter = ReferenceBindAdapter(state={"version": 1}, pending_changes={"version": 2})
    intent = ExecutionIntent(
        execution_intent_id="ei-legacy",
        decision_id="dec-legacy",
        request_id="req-legacy",
        policy_snapshot_id="policy-v1",
        actor_identity="operator",
        target_system="reference",
        target_resource="state",
        intended_action="mutate",
        decision_hash="a" * 64,
        decision_ts="2026-04-20T12:00:00Z",
        expected_state_fingerprint=adapter.fingerprint_state({"version": 1}),
    )

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.COMMITTED
