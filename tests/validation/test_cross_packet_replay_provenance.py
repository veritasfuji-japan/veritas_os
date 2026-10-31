"""Offline cross-packet replay and declared-provenance boundary tests.

All test packets, manifests, receipts and source IDs are synthetic. These tests
do not exercise execution, trusted issuance, signatures, persistent admission
or external audit. Never claim completeness beyond the supplied packet paths.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from scripts.validation.cross_packet_replay_provenance import (
    MAX_FILE_BYTES,
    MAX_PACKETS,
    main,
    verify_cross_packet_replay_provenance,
)
from veritas_os.governance.evidence_chain_manifest import (
    build_evidence_chain_manifest,
    with_manifest_hash,
)
from veritas_os.security.hash import canonical_json_dumps

ROOT = Path(__file__).resolve().parents[2]
PROFILE_FIXTURE = ROOT / "tests/validation/fixtures/synthetic_v0_2_example.json"
SAMPLE_TRACE = ROOT / "tests/validation/fixtures/sample_trace.txt"
COMMIT = "1" * 40
REPOSITORY = "example/synthetic-auditor"
AT = "2026-10-31T00:00:00+00:00"


def make_manifest(
    *,
    packet_id: str,
    operation_id: str,
    repository: str = REPOSITORY,
    source_commit: str = COMMIT,
    **overrides,
):
    manifest = build_evidence_chain_manifest(
        decision_id=f"decision-{operation_id}",
        execution_intent_id=f"intent-{operation_id}",
        operation_id=operation_id,
        action_class="read_only",
        target_system="mock-saas",
        target_resource="synthetic:item",
        requested_scope=["item:read"],
        final_outcome="commit",
        authority_evidence_id=f"authority-{operation_id}",
        authority_evidence_hash="a" * 64,
        outcome_receipt_id=f"outcome-{operation_id}",
        outcome_receipt_hash="b" * 64,
        bind_coverage_operation_id=operation_id,
        human_approval_required=False,
        generated_at=AT,
        metadata={
            "audit_packet_id": packet_id,
            "source_repository": repository,
            "source_commit": source_commit,
        },
    )
    if overrides:
        manifest = with_manifest_hash(replace(manifest, **overrides))
    return manifest


def write_packet(
    root: Path,
    *,
    label: str,
    packet_id: str,
    operation_id: str,
    repository: str = REPOSITORY,
    source_commit: str = COMMIT,
    manifest_overrides: dict | None = None,
) -> str:
    folder = root / label
    folder.mkdir(parents=True)
    obj = json.loads(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    obj["packet_id"] = packet_id
    obj["scope"]["repository"] = repository
    obj["scope"]["source_commit"] = source_commit
    obj["scope"]["execution_performed"] = True
    obj["scope"]["case_population"] = "one synthetic declared effect"
    case = obj["cases"][0]
    manifest = make_manifest(
        packet_id=packet_id,
        operation_id=operation_id,
        repository=repository,
        source_commit=source_commit,
    )
    if manifest_overrides:
        manifest = with_manifest_hash(replace(manifest, **manifest_overrides))
    case.update({
        "expectation": "ALLOW",
        "observed": "PASS",
        "actual_effect": "ALLOWED",
        "decision_id": manifest.decision_id,
        "intent_id": manifest.execution_intent_id,
        "authority_id": manifest.authority_evidence_id,
        "approval_id": None,
        "bind_receipt_id": None,
        "effect_receipt_id": manifest.outcome_receipt_id,
        "operation_id": operation_id,
        "manifest_id": manifest.manifest_id,
        "manifest_evidence_id": "EV-MANIFEST",
        "evidence_ids": ["EV-1", "EV-MANIFEST"],
    })
    raw = canonical_json_dumps(manifest.to_dict()).encode("utf-8")
    (folder / "manifest.json").write_bytes(raw)
    (folder / "sample_trace.txt").write_bytes(SAMPLE_TRACE.read_bytes())
    template = deepcopy(obj["evidence"][0])
    template.update({
        "id": "EV-MANIFEST",
        "class": "PROVENANCE",
        "relative_path": "manifest.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "notes": "Synthetic canonical manifest bytes; no external trust.",
    })
    obj["evidence"].append(template)
    (folder / "profile.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return f"{label}/profile.json"


def scan(root: Path, *paths: str, **kwargs):
    return verify_cross_packet_replay_provenance(
        packet_root=root, profile_paths=list(paths), **kwargs
    )


def codes(report: dict) -> set[str]:
    return {f["code"] for f in report["findings"]}


def test_two_distinct_packets_are_locally_consistent_not_authenticated(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-b")
    report = scan(tmp_path, b, a)
    assert report["status"] == "PASS", report
    assert report["validated_packet_count"] == 2
    assert report["bound_case_count"] == 2
    assert report["coverage"] == "EXPLICIT_CALLER_SUPPLIED_PACKETS_ONLY"
    assert report["external_origin_authenticated"] is False
    assert report["external_snapshot_anchor_verified"] is False
    assert all(row["origin_authentication"] == "NOT_PERFORMED" for row in report["link_records"])
    assert all(row["declared_provenance_binding"] == "CLAIMED_CONTEXT_MATCHES_LOCAL_MANIFEST" for row in report["link_records"])
    assert report["findings"] == []


def test_repeated_operation_in_separate_packets_is_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-x")
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-x")
    report = scan(tmp_path, a, b)
    assert report["status"] == "REPLAY_DETECTED", report
    assert "OPERATION_ID_REUSED" in codes(report)
    assert "MANIFEST_ID_REUSED" in codes(report)


def test_manifest_id_reused_with_distinct_operation_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    b = write_packet(
        tmp_path, label="b", packet_id="packet-b", operation_id="op-b",
        manifest_overrides={"manifest_id": "ecm-op-a"},
    )
    report = scan(tmp_path, a, b)
    assert report["status"] == "REPLAY_DETECTED"
    assert "MANIFEST_ID_REUSED" in codes(report)
    assert "OPERATION_ID_REUSED" not in codes(report)


def test_duplicate_packet_id_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    b = write_packet(tmp_path, label="b", packet_id="packet-a", operation_id="op-b")
    report = scan(tmp_path, a, b)
    assert report["status"] == "REPLAY_DETECTED"
    assert "PACKET_ID_REUSED" in codes(report)


def test_identical_manifest_bytes_in_two_packets_are_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-a")
    # Deliberately transplant a's whole manifest into b. Local profile bytes
    # are updated to make hashes internally consistent, but claimed packet
    # provenance is still conflicting.
    original = (tmp_path / "a/manifest.json").read_bytes()
    (tmp_path / "b/manifest.json").write_bytes(original)
    profile = json.loads((tmp_path / b).read_text())
    profile["evidence"][1]["sha256"] = hashlib.sha256(original).hexdigest()
    (tmp_path / b).write_text(json.dumps(profile))
    report = scan(tmp_path, a, b)
    assert report["status"] == "FAIL"
    assert "PROVENANCE_METADATA_MISMATCH" in codes(report)
    assert "MANIFEST_BYTES_REUSED" in codes(report)


def test_missing_provenance_metadata_incomplete_not_authenticated(tmp_path):
    a = write_packet(
        tmp_path, label="a", packet_id="packet-a", operation_id="op-a",
        manifest_overrides={"metadata": {"source_repository": REPOSITORY}},
    )
    report = scan(tmp_path, a)
    assert report["status"] == "INCOMPLETE"
    assert "PROVENANCE_METADATA_MISSING" in codes(report)
    assert report["link_records"][0]["origin_authentication"] == "NOT_PERFORMED"


def test_mismatched_claimed_source_commit_fails(tmp_path):
    a = write_packet(
        tmp_path, label="a", packet_id="packet-a", operation_id="op-a",
        manifest_overrides={"metadata": {
            "audit_packet_id": "packet-a",
            "source_repository": REPOSITORY,
            "source_commit": "2" * 40,
        }},
    )
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "PROVENANCE_METADATA_MISMATCH" in codes(report)


def test_different_repository_namespaces_allow_same_operation_id(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-common")
    b = write_packet(
        tmp_path, label="b", packet_id="packet-b", operation_id="op-common",
        repository="different/synthetic-namespace",
    )
    report = scan(tmp_path, a, b)
    assert report["status"] == "PASS", report


def test_conflicting_manifest_identifiers_fail(tmp_path):
    a = write_packet(
        tmp_path, label="a", packet_id="packet-a", operation_id="op-a",
        manifest_overrides={"operation_id": "op-substituted"},
    )
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "OPERATION_OR_MANIFEST_MISMATCH" in codes(report)


def test_conflicting_decision_id_fails(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    profile = json.loads((tmp_path / a).read_text())
    profile["cases"][0]["decision_id"] = "decision-unrelated"
    (tmp_path / a).write_text(json.dumps(profile))
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "CASE_MANIFEST_LINK_ID_MISMATCH" in codes(report)


def test_tampered_manifest_bytes_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    (tmp_path / "a/manifest.json").write_bytes(b"{}")
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "PROFILE_VALIDATION_FAILED" in codes(report)


def test_wrong_manifest_internal_hash_rejected_even_when_profile_hash_matches(tmp_path):
    a = write_packet(
        tmp_path, label="a", packet_id="packet-a", operation_id="op-a",
        manifest_overrides={"manifest_hash": "e" * 64},
    )
    # with_manifest_hash recomputes the final hash; corrupt the canonical file
    # and update its profile reference, to test the nested digest check.
    path = tmp_path / "a/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["manifest_hash"] = "e" * 64
    raw = canonical_json_dumps(manifest).encode("utf-8")
    path.write_bytes(raw)
    profile = json.loads((tmp_path / a).read_text())
    profile["evidence"][1]["sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / a).write_text(json.dumps(profile))
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "MANIFEST_EVIDENCE_INVALID" in codes(report)


def test_noncanonical_manifest_bytes_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    path = tmp_path / "a/manifest.json"
    object_data = json.loads(path.read_bytes())
    raw = json.dumps(object_data, indent=2).encode("utf-8")
    path.write_bytes(raw)
    profile = json.loads((tmp_path / a).read_text())
    profile["evidence"][1]["sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / a).write_text(json.dumps(profile))
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "MANIFEST_EVIDENCE_INVALID" in codes(report)


@pytest.mark.parametrize("path", [
    "../outside/profile.json", "/etc/passwd", "./a/profile.json",
    "a/../a/profile.json", "a//profile.json", "a\\profile.json",
])
def test_unsafe_packet_paths_rejected(tmp_path, path):
    report = scan(tmp_path, path)
    assert report["status"] == "FAIL"
    assert "UNREADABLE_OR_UNSUPPORTED_PROFILE" in codes(report)


def test_symlinked_packet_directory_is_rejected(tmp_path):
    name = write_packet(tmp_path, label="real", packet_id="packet-a", operation_id="op-a")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    report = scan(tmp_path, "link/profile.json")
    assert report["status"] == "FAIL"
    assert "UNREADABLE_OR_UNSUPPORTED_PROFILE" in codes(report)
    assert scan(tmp_path, name)["status"] == "PASS"


def test_symlinked_manifest_is_rejected(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    p = tmp_path / "a/manifest.json"
    p.rename(tmp_path / "a/real-manifest.json")
    p.symlink_to(tmp_path / "a/real-manifest.json")
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "PROFILE_VALIDATION_FAILED" in codes(report)


def test_oversized_profile_rejected_without_unbounded_read(tmp_path):
    folder = tmp_path / "a"
    folder.mkdir()
    with (folder / "profile.json").open("wb") as file:
        file.truncate(MAX_FILE_BYTES + 1)
    report = scan(tmp_path, "a/profile.json")
    assert report["status"] == "FAIL"
    assert "UNREADABLE_OR_UNSUPPORTED_PROFILE" in codes(report)


def test_empty_oversized_and_duplicate_packet_sets_fail(tmp_path):
    assert scan(tmp_path)["status"] == "FAIL"
    assert "INVALID_PACKET_SET" in codes(scan(tmp_path))
    assert scan(tmp_path, *(["absent/profile.json"] * (MAX_PACKETS + 1)))["status"] == "FAIL"
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    report = scan(tmp_path, a, a)
    assert report["status"] == "FAIL"
    assert "DUPLICATE_INPUT_PATH" in codes(report)


def test_legacy_v01_profile_is_not_accepted(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    obj = json.loads((tmp_path / a).read_text())
    obj["profile_version"] = "veritas.audit-evidence-profile/0.1"
    (tmp_path / a).write_text(json.dumps(obj))
    report = scan(tmp_path, a)
    assert report["status"] == "FAIL"
    assert "UNREADABLE_OR_UNSUPPORTED_PROFILE" in codes(report)


def test_input_order_does_not_change_report_bytes(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-b")
    first = scan(tmp_path, a, b)
    second = scan(tmp_path, b, a)
    assert canonical_json_dumps(first) == canonical_json_dumps(second)


def test_snapshot_digest_can_be_rechecked_but_is_not_independent_anchor(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    first = scan(tmp_path, a)
    assert first["status"] == "PASS"
    matching = scan(tmp_path, a, expected_snapshot_digest=first["snapshot_digest"])
    assert matching["status"] == "PASS"
    assert matching["expected_digest_comparison"] == "MATCHED_CALLER_SUPPLIED_DIGEST"
    assert matching["external_snapshot_anchor_verified"] is False
    mismatch = scan(tmp_path, a, expected_snapshot_digest="0" * 64)
    assert mismatch["status"] == "FAIL"
    assert "SNAPSHOT_DIGEST_MISMATCH" in codes(mismatch)


def test_omitted_prior_packet_is_invisible_and_explicitly_disclosed(tmp_path):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-shared")
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-shared")
    assert scan(tmp_path, a, b)["status"] == "REPLAY_DETECTED"
    partial = scan(tmp_path, b)
    assert partial["status"] == "PASS"
    assert "omitted history is invisible" in " ".join(partial["limitations"])


def test_unbound_unexecuted_case_produces_incomplete_report(tmp_path):
    folder = tmp_path / "unbound"
    folder.mkdir()
    obj = json.loads(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    (folder / "sample_trace.txt").write_bytes(SAMPLE_TRACE.read_bytes())
    (folder / "profile.json").write_text(json.dumps(obj))
    report = scan(tmp_path, "unbound/profile.json")
    assert report["status"] == "INCOMPLETE"
    assert "UNBOUND_CASE" in codes(report)
    assert "NO_BOUND_OPERATIONS" in codes(report)


def test_cli_reports_json_and_nonzero_for_replay(tmp_path, capsys):
    a = write_packet(tmp_path, label="a", packet_id="packet-a", operation_id="op-a")
    assert main([str(tmp_path), a]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    b = write_packet(tmp_path, label="b", packet_id="packet-b", operation_id="op-a")
    assert main([str(tmp_path), a, b]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "REPLAY_DETECTED"
