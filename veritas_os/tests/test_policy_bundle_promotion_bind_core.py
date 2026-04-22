"""Tests that policy bundle promotion is wired through bind-core adjudication."""

from __future__ import annotations

from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome
from veritas_os.policy.policy_bundle_promotion import promote_policy_bundle_with_bind_boundary


def test_promotion_uses_bind_core_entrypoint(monkeypatch, tmp_path) -> None:
    called = {"value": False}

    def _fake_execute_bind_adjudication(**kwargs):
        called["value"] = True
        intent = kwargs["execution_intent"]
        return BindReceipt(
            bind_receipt_id="br-core",
            execution_intent_id=intent.execution_intent_id,
            decision_id=intent.decision_id,
            bind_ts="2026-04-20T12:00:10Z",
            final_outcome=FinalOutcome.COMMITTED,
        )

    monkeypatch.setattr(
        "veritas_os.policy.policy_bundle_promotion.execute_bind_adjudication",
        _fake_execute_bind_adjudication,
    )

    bundle_dir = tmp_path / "bundles" / "bundle-v2"
    (bundle_dir / "compiled").mkdir(parents=True)
    (bundle_dir / "compiled" / "canonical_ir.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "manifest.sig").write_text("sig", encoding="utf-8")

    receipt = promote_policy_bundle_with_bind_boundary(
        decision_id="dec-1",
        request_id="req-1",
        actor_identity="role-admin",
        policy_snapshot_id="snap-1",
        decision_hash="a" * 64,
        target_bundle_dir=bundle_dir,
        pointer_path=tmp_path / "runtime" / "active_bundle.json",
        allowed_root=tmp_path / "bundles",
        append_trustlog=False,
    )

    assert called["value"] is True
    assert receipt.final_outcome is FinalOutcome.COMMITTED
