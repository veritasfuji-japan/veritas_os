"""Pure offline verification for separately pinned audit registry checkpoints."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.validation.audit_registry_checkpoint_v0_1 import (
    _digest,
    compare_pinned_checkpoint,
    validate_checkpoint,
)


def checkpoint(packets=("packet-a",), *, label="first"):
    roster = [
        {"packet_id": p, "packet_hash": _digest([label, p]), "case_count": 1}
        for p in packets
    ]
    content = {
        "format_version": "veritas.audit-registry-checkpoint/0.1",
        "packet_count": len(roster),
        "case_count": len(roster),
        "packets": roster,
    }
    candidate = {
        **content,
        "scope": "LOCAL_UNAUTHENTICATED_AUDIT_INVENTORY",
        "origin_authentication": "NOT_PERFORMED",
        "external_anchor": "NOT_EMBEDDED",
        "snapshot_root": _digest(content),
    }
    candidate["checkpoint_hash"] = _digest(candidate)
    return candidate


def test_valid_untrusted_checkpoint_is_self_consistent():
    assert validate_checkpoint(checkpoint())
    assert validate_checkpoint(checkpoint(("packet-a", "packet-b")))


def test_independent_pin_required_and_identical_history_only_unauthenticated():
    baseline = checkpoint()
    assert compare_pinned_checkpoint(
        current=deepcopy(baseline), reference=baseline,
        pinned_reference_sha256=_digest(baseline),
    ) == "HISTORY_UNCHANGED_UNAUTHENTICATED"
    assert compare_pinned_checkpoint(
        current=baseline, reference=baseline, pinned_reference_sha256="",
    ) == "ANCHOR_REQUIRED"


def test_trusted_baseline_allows_append_without_claiming_global_completeness():
    baseline = checkpoint(("packet-a",))
    extended = checkpoint(("packet-a", "packet-b"))
    assert compare_pinned_checkpoint(
        current=extended, reference=baseline,
        pinned_reference_sha256=_digest(baseline),
    ) == "HISTORY_EXTENDED_UNAUTHENTICATED"


def test_rollback_or_changed_committed_bytes_detected():
    baseline = checkpoint(("packet-a", "packet-b"))
    missing = checkpoint(("packet-a",))
    mutated = checkpoint(("packet-a", "packet-b"), label="different")
    for current in (missing, mutated):
        assert compare_pinned_checkpoint(
            current=current, reference=baseline,
            pinned_reference_sha256=_digest(baseline),
        ) == "HISTORY_DIVERGED"


@pytest.mark.parametrize("change", [
    lambda x: x.update(origin_authentication="VERIFIED"),
    lambda x: x.update(external_anchor="SIGNED"),
    lambda x: x.update(scope="EXECUTION_AUTHORIZATION"),
    lambda x: x.update(packet_count=True),
    lambda x: x.update(case_count=1_000_000),
    lambda x: x.update(snapshot_root="0" * 64),
    lambda x: x["packets"][0].update(packet_hash="INVALID"),
    lambda x: x["packets"][0].update(case_count=0),
    lambda x: x.update(extra_field="true"),
    lambda x: x["packets"].append(x["packets"][0].copy()),
])
def test_malformed_or_false_authority_is_rejected_even_if_rehashed(change):
    baseline = checkpoint()
    change(baseline)
    if baseline["snapshot_root"] != "0" * 64:
        baseline["snapshot_root"] = _digest({
            k: baseline[k] for k in (
                "format_version", "packet_count", "case_count", "packets",
            )
        })
    baseline["checkpoint_hash"] = _digest({
        k: v for k, v in baseline.items() if k != "checkpoint_hash"
    })
    assert not validate_checkpoint(baseline)


def test_replaced_reference_cannot_move_trusted_baseline_even_if_self_hashed():
    baseline = checkpoint(("packet-a", "packet-b"))
    pin = _digest(baseline)
    attacker = checkpoint(("packet-a",))
    assert validate_checkpoint(attacker)
    assert compare_pinned_checkpoint(
        current=attacker, reference=attacker, pinned_reference_sha256=pin,
    ) == "REFERENCE_ANCHOR_MISMATCH"
