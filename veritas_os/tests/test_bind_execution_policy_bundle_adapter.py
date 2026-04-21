"""Tests for real policy bundle promotion bind-boundary adapter."""

from __future__ import annotations

import hashlib
import json

from veritas_os.logging.encryption import generate_key
from veritas_os.policy.bind_artifacts import ExecutionIntent, FinalOutcome, find_bind_receipts
from veritas_os.policy.bind_boundary_adapters import PolicyBundlePromotionAdapter
from veritas_os.policy.bind_execution import execute_bind_boundary


def _write_bundle(bundle_dir, *, with_signature: bool) -> None:
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


def _intent(*, bundle_dir: str, expected_fingerprint: str, approved: bool = True) -> ExecutionIntent:
    return ExecutionIntent(
        execution_intent_id="ei-policy-bundle",
        decision_id="dec-policy-bundle",
        request_id="req-policy-bundle",
        policy_snapshot_id="policy-snapshot-1",
        actor_identity="governance-operator",
        target_system="governance",
        target_resource=bundle_dir,
        intended_action="promote_policy_bundle",
        decision_hash="b" * 64,
        decision_ts="2026-04-20T12:00:00Z",
        expected_state_fingerprint=expected_fingerprint,
        approval_context={"policy_bundle_promotion_approved": approved},
    )


def test_real_adapter_successful_commit(tmp_path) -> None:
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

    adapter = PolicyBundlePromotionAdapter(
        pointer_path=pointer_path,
        allowed_root=bundles_root,
        require_signature=True,
    )
    before_snapshot = adapter.snapshot()
    assert before_snapshot == adapter.snapshot()

    intent = _intent(
        bundle_dir=str(new_bundle.resolve()),
        expected_fingerprint=adapter.fingerprint_state(before_snapshot),
    )
    receipt = execute_bind_boundary(
        execution_intent=intent,
        adapter=adapter,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    stored_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert stored_pointer["active_bundle_dir"] == str(new_bundle.resolve())


def test_real_adapter_blocked_bind_by_authority(tmp_path) -> None:
    bundles_root = tmp_path / "bundles"
    bundle = bundles_root / "bundle-v1"
    _write_bundle(bundle, with_signature=True)

    pointer_path = tmp_path / "runtime" / "active_bundle.json"
    adapter = PolicyBundlePromotionAdapter(pointer_path=pointer_path, allowed_root=bundles_root)
    snapshot = adapter.snapshot()

    intent = _intent(
        bundle_dir=str(bundle.resolve()),
        expected_fingerprint=adapter.fingerprint_state(snapshot),
        approved=False,
    )
    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert not pointer_path.exists()


def test_real_adapter_postcondition_failure_rolls_back(tmp_path) -> None:
    bundles_root = tmp_path / "bundles"
    old_bundle = bundles_root / "bundle-v1"
    new_bundle = bundles_root / "bundle-v2"
    _write_bundle(old_bundle, with_signature=True)
    _write_bundle(new_bundle, with_signature=False)

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

    adapter = PolicyBundlePromotionAdapter(
        pointer_path=pointer_path,
        allowed_root=bundles_root,
        require_signature=True,
    )
    intent = _intent(
        bundle_dir=str(new_bundle.resolve()),
        expected_fingerprint=adapter.fingerprint_state(adapter.snapshot()),
    )
    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter, append_trustlog=False)

    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    restored_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert restored_pointer["active_bundle_dir"] == str(old_bundle.resolve())


def test_real_adapter_trustlog_lineage_and_receipt(tmp_path, monkeypatch) -> None:
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

    bundles_root = tmp_path / "bundles"
    bundle = bundles_root / "bundle-v1"
    _write_bundle(bundle, with_signature=True)

    pointer_path = tmp_path / "runtime" / "active_bundle.json"
    adapter = PolicyBundlePromotionAdapter(
        pointer_path=pointer_path,
        allowed_root=bundles_root,
        require_signature=True,
    )
    intent = _intent(
        bundle_dir=str(bundle.resolve()),
        expected_fingerprint=adapter.fingerprint_state(adapter.snapshot()),
    )

    receipt = execute_bind_boundary(execution_intent=intent, adapter=adapter)

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert receipt.trustlog_hash
    by_decision = find_bind_receipts(decision_id=intent.decision_id)
    by_intent = find_bind_receipts(execution_intent_id=intent.execution_intent_id)
    by_receipt = find_bind_receipts(bind_receipt_id=receipt.bind_receipt_id)
    assert len(by_decision) == 1
    assert len(by_intent) == 1
    assert len(by_receipt) == 1
