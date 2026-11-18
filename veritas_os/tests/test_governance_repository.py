"""Governance repository abstraction regression tests."""

from __future__ import annotations

import errno
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest

from veritas_os.api import governance as gov
from veritas_os.governance.file_repository import FileGovernanceRepository
from veritas_os.governance.repository import GovernanceHistoryWriteError, GovernanceRecoveryRequiredError, GovernanceWriteConflictError


@pytest.fixture(autouse=True)
def _reset_repo_factory() -> None:
    gov.set_governance_repository_factory(None)
    yield
    gov.set_governance_repository_factory(None)


def test_file_repository_roundtrip(tmp_path):
    """File repository persists current policy and history with rollback records."""
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "governance.json",
        history_path=tmp_path / "governance_history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
    )

    default = repo.get_current_policy(
        default_factory=lambda: gov.GovernancePolicy().model_dump()
    )
    assert default["version"] == "governance_v1"

    updated = {**default, "version": "governance_v2", "updated_by": "alice"}
    repo.update_policy(
        previous=default,
        updated=updated,
        proposer="alice",
        approvers=["r1", "r2"],
        event_type="update",
    )
    assert repo.get_current_policy(default_factory=dict)["version"] == "governance_v2"

    restored = {**default, "version": "governance_v1_rollback", "updated_by": "bob"}
    repo.rollback_policy(
        previous=updated,
        restored=restored,
        proposer="bob",
        approvers=["r3", "r4"],
    )

    history = repo.list_policy_history(limit=10, max_records=500)
    assert len(history) == 2
    assert history[0]["event_type"] == "rollback"
    assert history[1]["event_type"] == "update"


@pytest.mark.parametrize("operation", ["update", "rollback"])
def test_file_repository_rejects_stale_writes(tmp_path, operation):
    """Keep the winning policy and history when another writer is stale."""
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
    )
    original = repo.get_current_policy(default_factory=dict)
    winner = {"version": "winner"}
    repo.update_policy(
        previous=original, updated=winner, proposer="alice",
        approvers=[], event_type="update",
    )

    with pytest.raises(GovernanceWriteConflictError):
        if operation == "update":
            repo.update_policy(
                previous=original, updated={"version": "stale"}, proposer="bob",
                approvers=[], event_type="update",
            )
        else:
            repo.rollback_policy(
                previous=original, restored={"version": "stale"}, proposer="bob",
                approvers=[],
            )

    assert repo.get_current_policy(default_factory=dict) == winner
    assert [record["new_policy"] for record in repo.list_policy_history(
        limit=10, max_records=10
    )] == [winner]


def test_file_repository_serializes_independent_writers(tmp_path):
    """Only one worker can initialize a policy from the same missing state."""
    pytest.importorskip("fcntl", exc_type=ImportError)
    start = threading.Barrier(2)

    def update(version):
        repo = FileGovernanceRepository(
            policy_path=tmp_path / "policy.json",
            history_path=tmp_path / "history.jsonl",
            lock=threading.Lock(),
            policy_history_max=10,
        )
        previous = repo.get_current_policy(default_factory=dict)
        start.wait(timeout=5)
        try:
            repo.update_policy(
                previous=previous,
                updated={"version": version},
                proposer=version,
                approvers=[],
                event_type="update",
            )
        except GovernanceWriteConflictError:
            return None
        return version

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [result for result in pool.map(update, ["alice", "bob"]) if result]
    assert len(winners) == 1
    assert json.loads((tmp_path / "policy.json").read_text()) == {"version": winners[0]}
    assert len((tmp_path / "history.jsonl").read_text().splitlines()) == 1


def test_governance_policy_write_holds_lock_until_history_append(tmp_path, monkeypatch):
    """Other workers cannot start writing before the current event is recorded."""
    fcntl = pytest.importorskip("fcntl", exc_type=ImportError)
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
    )
    original_append = repo._append_policy_event_locked

    def check_lock(event):
        with (tmp_path / "policy.json.lock").open("rb") as other_writer:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other_writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        original_append(event)

    monkeypatch.setattr(repo, "_append_policy_event_locked", check_lock)
    repo.update_policy(
        previous={}, updated={"version": "v1"}, proposer="operator",
        approvers=[], event_type="update",
    )
    assert repo.list_policy_history(limit=1, max_records=10)[0]["new_version"] == "v1"


@pytest.mark.parametrize("stage", ["before_policy", "before_history", "after_history"])
@pytest.mark.parametrize("operation", ["update", "rollback"])
def test_pending_policy_change_recovers_once_after_interruption(
    tmp_path, monkeypatch, stage, operation
):
    """Reopening completes the journaled operation without duplicating its event."""
    policy_path = tmp_path / "policy.json"
    history_path = tmp_path / "history.jsonl"

    def repository():
        return FileGovernanceRepository(
            policy_path=policy_path, history_path=history_path,
            lock=threading.Lock(), policy_history_max=10,
        )

    repo = repository()
    initial = {"version": "initial"}
    repo.save_policy(initial)
    updated = {"version": "updated"}

    def stop_before_policy(_policy):
        raise SystemExit("simulated process interruption")

    append = repo._append_policy_event_locked

    def stop_at_history(event):
        if stage == "after_history":
            append(event)
        raise SystemExit("simulated process interruption")

    with monkeypatch.context() as patcher:
        if stage == "before_policy":
            patcher.setattr(repo, "_save_policy_locked", stop_before_policy)
        else:
            patcher.setattr(repo, "_append_policy_event_locked", stop_at_history)
        with pytest.raises(SystemExit):
            if operation == "rollback":
                repo.rollback_policy(
                    previous=initial, restored=updated, proposer="operator", approvers=[],
                )
            else:
                repo.update_policy(
                    previous=initial, updated=updated, proposer="operator",
                    approvers=[], event_type="update",
                )

    assert policy_path.with_name("policy.json.pending.json").exists()
    expected = initial if stage == "before_policy" else updated
    assert repository().get_current_policy(default_factory=dict) == expected
    for _ in range(2):
        history = repository().list_policy_history(limit=10, max_records=10)
        if stage == "before_policy":
            assert history == []
        else:
            assert len(history) == 1
            assert history[0]["event_id"]
            assert history[0]["new_policy"] == updated
    assert not policy_path.with_name("policy.json.pending.json").exists()


def test_recovery_refuses_divergent_policy(tmp_path, monkeypatch):
    """A pending operation must not overwrite an unrelated policy."""
    policy_path = tmp_path / "policy.json"
    repo = FileGovernanceRepository(
        policy_path=policy_path, history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(), policy_history_max=10,
    )

    def stop(_policy):
        raise SystemExit("simulated interruption")

    with monkeypatch.context() as patcher:
        patcher.setattr(repo, "_save_policy_locked", stop)
        with pytest.raises(SystemExit):
            repo.update_policy(
                previous={}, updated={"version": "pending"}, proposer="operator",
                approvers=[], event_type="update",
            )
    divergent = {"version": "external"}
    policy_path.write_text(json.dumps(divergent))

    with pytest.raises(GovernanceRecoveryRequiredError):
        repo.get_current_policy(default_factory=dict)
    assert json.loads(policy_path.read_bytes()) == divergent
    assert repo._pending_path.exists()


@pytest.mark.parametrize("stage", ["before_history", "after_history"])
def test_recovery_serializes_processes_after_writer_exit(tmp_path, stage):
    """Independent processes recover one event after an abrupt writer exit."""
    import multiprocessing
    import os

    pytest.importorskip("fcntl", exc_type=ImportError)
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("fork is unavailable")
    context = multiprocessing.get_context("fork")
    policy_path = tmp_path / "policy.json"
    history_path = tmp_path / "history.jsonl"

    def repository():
        return FileGovernanceRepository(
            policy_path=policy_path, history_path=history_path,
            lock=threading.Lock(), policy_history_max=10,
        )

    def interrupted_writer():
        repo = repository()
        append = repo._append_policy_event_locked

        def interrupt(event):
            if stage == "after_history":
                append(event)
            os._exit(73)

        repo._append_policy_event_locked = interrupt
        repo.update_policy(
            previous={}, updated={"version": "saved"}, proposer="operator",
            approvers=[], event_type="update",
        )

    writer = context.Process(target=interrupted_writer)
    writer.start()
    try:
        writer.join(timeout=15)
        assert writer.exitcode == 73
    finally:
        if writer.is_alive():
            writer.terminate()
            writer.join(timeout=5)
    assert repository()._pending_path.exists()
    start = context.Barrier(2)
    results = context.Queue()

    def recover():
        repo = repository()
        start.wait(timeout=10)
        results.put(repo.get_current_policy(default_factory=dict))

    readers = [context.Process(target=recover) for _ in range(2)]
    try:
        for reader in readers:
            reader.start()
        for reader in readers:
            reader.join(timeout=15)
            assert reader.exitcode == 0
        assert [results.get(timeout=2) for _ in readers] == [{"version": "saved"}] * 2
    finally:
        for reader in readers:
            if reader.is_alive():
                reader.terminate()
                reader.join(timeout=5)
        results.close()
        results.join_thread()
    records = repository().list_policy_history(limit=10, max_records=10)
    assert len(records) == 1
    assert records[0]["new_policy"] == {"version": "saved"}
    assert not repository()._pending_path.exists()


def test_corrupt_recovery_journal_blocks_policy_reads(tmp_path):
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json", history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(), policy_history_max=10,
    )
    repo._pending_path.write_bytes(b"{")
    with pytest.raises(GovernanceRecoveryRequiredError):
        repo.get_current_policy(default_factory=dict)
    assert repo._pending_path.read_bytes() == b"{"


@pytest.mark.parametrize("stage", ["before_policy", "before_history", "after_history"])
@pytest.mark.parametrize("corruption", [
    "previous_digest", "new_digest", "previous_version", "new_version",
    "previous_policy", "invalid_previous_policy", "new_policy_boolean",
    "missing_approvers", "invalid_approvers", "invalid_approver",
    "changed_at", "changed_by", "proposer", "event_type",
    "changed_at_value", "changed_by_value",
])
def test_recovery_rejects_inconsistent_event(tmp_path, monkeypatch, stage, corruption):
    """Journal recovery must not publish or discard an inconsistent transition."""
    from veritas_os.policy.governance_identity import compute_governance_digest

    policy_path = tmp_path / "policy.json"
    history_path = tmp_path / "history.jsonl"
    repo = FileGovernanceRepository(
        policy_path=policy_path, history_path=history_path,
        lock=threading.Lock(), policy_history_max=10,
    )
    previous = {"version": "initial"}
    repo.save_policy(previous)
    updated = {
        "version": "updated", "enabled": 1, "updated_by": "operator",
        "updated_at": "2026-11-18T00:00:00+00:00",
    }
    append = repo._append_policy_event_locked

    def interrupt(value):
        if stage == "after_history":
            append(value)
        raise SystemExit("simulated interruption")

    with monkeypatch.context() as patcher:
        target = "_save_policy_locked" if stage == "before_policy" else "_append_policy_event_locked"
        patcher.setattr(repo, target, interrupt)
        with pytest.raises(SystemExit):
            repo.update_policy(
                previous=previous, updated=updated, proposer="operator",
                approvers=[], event_type="update",
            )

    pending = json.loads(repo._pending_path.read_text())
    event = pending["event"]
    if corruption in {"previous_digest", "new_digest"}:
        event[corruption] = "0" * 64
    elif corruption in {"previous_version", "new_version"}:
        event[corruption] = "incorrect-version"
    elif corruption == "previous_policy":
        event["previous_policy"] = {"version": "unrelated"}
        event["previous_version"] = "unrelated"
        event["previous_digest"] = compute_governance_digest(event["previous_policy"])
    elif corruption == "invalid_previous_policy":
        event["previous_policy"] = []
    elif corruption == "missing_approvers":
        del event["approvers"]
    elif corruption == "invalid_approvers":
        event["approvers"] = None
    elif corruption == "invalid_approver":
        event["approvers"] = [1]
    elif corruption in {"changed_at", "changed_by", "proposer", "event_type"}:
        event[corruption] = None
    elif corruption in {"changed_at_value", "changed_by_value"}:
        event[corruption.removesuffix("_value")] = "incorrect-value"
    else:
        # Python equality considers 1 == True, but their policy digests differ.
        event["new_policy"]["enabled"] = True
    repo._pending_path.write_text(json.dumps(pending))
    journal_bytes = repo._pending_path.read_bytes()
    policy_bytes = policy_path.read_bytes()
    history_bytes = history_path.read_bytes() if history_path.exists() else None

    operations = [
        lambda: repo.get_current_policy(default_factory=dict),
        lambda: repo.list_policy_history(limit=10, max_records=10),
        lambda: repo.save_policy({"version": "must-not-save"}),
    ]
    for operation in operations:
        with pytest.raises(GovernanceRecoveryRequiredError):
            operation()
        assert repo._pending_path.read_bytes() == journal_bytes
        assert policy_path.read_bytes() == policy_bytes
        assert (history_path.read_bytes() if history_path.exists() else None) == history_bytes


def test_recovery_preserves_initial_default_policy_provenance(tmp_path, monkeypatch):
    """A first write can start from application defaults without a policy file."""
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json", history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(), policy_history_max=10,
    )
    previous = gov.GovernancePolicy().model_dump()
    updated = {**previous, "version": "updated"}

    def interrupt(_event):
        raise SystemExit("simulated interruption")

    with monkeypatch.context() as patcher:
        patcher.setattr(repo, "_append_policy_event_locked", interrupt)
        with pytest.raises(SystemExit):
            repo.update_policy(
                previous=previous, updated=updated, proposer="operator",
                approvers=[], event_type="update",
            )
    assert json.loads(repo._pending_path.read_text())["previous"] is None
    assert repo.get_current_policy(default_factory=dict) == updated
    records = repo.list_policy_history(limit=10, max_records=10)
    assert len(records) == 1
    assert records[0]["previous_policy"] == previous
    assert not repo._pending_path.exists()


def test_recovery_rejects_type_conflicting_existing_event(tmp_path, monkeypatch):
    """A matching event ID must not hide bool-versus-number content conflicts."""
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json", history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(), policy_history_max=10,
    )
    append = repo._append_policy_event_locked

    def interrupt(event):
        append(event)
        raise SystemExit("simulated interruption")

    with monkeypatch.context() as patcher:
        patcher.setattr(repo, "_append_policy_event_locked", interrupt)
        with pytest.raises(SystemExit):
            repo.update_policy(
                previous={}, updated={"version": "updated", "enabled": 1},
                proposer="operator", approvers=[], event_type="update",
            )
    record = json.loads(repo._history_path.read_text())
    record["new_policy"]["enabled"] = True
    repo._history_path.write_text(json.dumps(record) + "\n")
    history_bytes = repo._history_path.read_bytes()
    journal_bytes = repo._pending_path.read_bytes()
    with pytest.raises(GovernanceRecoveryRequiredError):
        repo.get_current_policy(default_factory=dict)
    assert repo._history_path.read_bytes() == history_bytes
    assert repo._pending_path.read_bytes() == journal_bytes


@pytest.mark.parametrize("has_atomic_io", [True, False])
def test_history_trim_sync_failure_preserves_recovery_journal(
    tmp_path, monkeypatch, has_atomic_io
):
    """A trimmed history must be directory-synced before discarding recovery."""
    import os
    import stat

    if not hasattr(os, "O_DIRECTORY"):
        pytest.skip("directory descriptors are unavailable")
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    history_path = history_dir / "events.jsonl"
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json", history_path=history_path,
        lock=threading.Lock(), policy_history_max=1, has_atomic_io=has_atomic_io,
    )
    initial = {"version": "initial"}
    repo.update_policy(
        previous={}, updated=initial, proposer="operator",
        approvers=[], event_type="update",
    )
    history_inode = history_dir.stat().st_ino
    fsync, replace_file = os.fsync, os.replace
    trimmed = False

    def track_history_replace(source, destination):
        nonlocal trimmed
        result = replace_file(source, destination)
        if Path(destination) == history_path:
            trimmed = True
        return result

    def fail_trimmed_history_sync(fd):
        info = os.fstat(fd)
        if trimmed and stat.S_ISDIR(info.st_mode) and info.st_ino == history_inode:
            raise OSError(errno.EIO, "trimmed history directory sync failed")
        fsync(fd)

    updated = {"version": "updated"}
    with monkeypatch.context() as patcher:
        patcher.setattr(os, "replace", track_history_replace)
        patcher.setattr(os, "fsync", fail_trimmed_history_sync)
        with pytest.raises(GovernanceHistoryWriteError):
            repo.update_policy(
                previous=initial, updated=updated, proposer="operator",
                approvers=[], event_type="update",
            )
        assert trimmed
        assert repo._pending_path.exists()
        with pytest.raises(GovernanceRecoveryRequiredError):
            repo.get_current_policy(default_factory=dict)
        assert repo._pending_path.exists()

    assert repo.get_current_policy(default_factory=dict) == updated
    assert not repo._pending_path.exists()
    records = repo.list_policy_history(limit=10, max_records=10)
    assert len(records) == 1
    assert records[0]["new_policy"] == updated


def test_governance_reports_history_failure_after_saving_policy(tmp_path):
    history_path = tmp_path / "history.jsonl"
    history_path.mkdir()
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=10,
    )
    updated = {"version": "saved"}
    with pytest.raises(GovernanceHistoryWriteError, match="GOVERNANCE_POLICY_HISTORY_WRITE_FAILED"):
        repo.update_policy(
            previous={}, updated=updated, proposer="operator",
            approvers=[], event_type="update",
        )
    with pytest.raises(GovernanceRecoveryRequiredError):
        repo.get_current_policy(default_factory=dict)
    history_path.rmdir()
    assert repo.get_current_policy(default_factory=dict) == updated
    assert len(repo.list_policy_history(limit=10, max_records=10)) == 1


@pytest.mark.parametrize("sync_errno", [errno.EIO, errno.EINVAL, errno.ENOTSUP])
def test_governance_history_directory_sync_failure(tmp_path, monkeypatch, caplog, sync_errno):
    """Unsupported directory sync warns and actual I/O failure propagates."""
    import os
    import stat

    if not hasattr(os, "O_DIRECTORY"):
        pytest.skip("directory descriptors are unavailable")
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    history_path = history_dir / "events.jsonl"
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=10,
    )
    history_inode = history_dir.stat().st_ino
    fsync = os.fsync

    def fail_history_directory_sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode) and info.st_ino == history_inode:
            raise OSError(sync_errno, "directory sync failed")
        fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_history_directory_sync)
    changes = {
        "previous": {}, "updated": {"version": "saved"}, "proposer": "operator",
        "approvers": [], "event_type": "update",
    }
    if sync_errno == errno.EIO:
        with pytest.raises(GovernanceHistoryWriteError):
            repo.update_policy(**changes)
    else:
        repo.update_policy(**changes)
        assert "Governance directory sync unsupported" in caplog.text
    monkeypatch.setattr(os, "fsync", fsync)
    assert repo.list_policy_history(limit=1, max_records=10)[0]["new_version"] == "saved"
    assert repo.get_current_policy(default_factory=dict)["version"] == "saved"


def test_fallback_policy_save_preserves_other_file_with_same_stem(tmp_path):
    """A policy write uses its own temporary file and preserves sibling files."""
    sibling = tmp_path / "policy.tmp"
    sibling.write_bytes(b"existing data")
    policy_path = tmp_path / "policy.json"
    repo = FileGovernanceRepository(
        policy_path=policy_path,
        history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
        has_atomic_io=False,
    )

    repo.save_policy({"version": "saved"})

    assert sibling.read_bytes() == b"existing data"
    assert json.loads(policy_path.read_bytes()) == {"version": "saved"}
    assert not list(tmp_path.glob(".policy.json.*.tmp"))


def test_fallback_policy_syncs_directory_after_replace(tmp_path, monkeypatch, caplog):
    """A directory sync failure after replacement still allows audit history."""
    policy_path = tmp_path / "policies" / "policy.json"
    history_path = tmp_path / "history" / "events.jsonl"
    repo = FileGovernanceRepository(
        policy_path=policy_path,
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=10,
        has_atomic_io=False,
    )
    updated = {"version": "saved"}
    synced = []

    def sync_directory(directory):
        synced.append(directory)
        if directory == policy_path.parent:
            assert json.loads(policy_path.read_text(encoding="utf-8")) == updated
            raise OSError("directory sync failed")

    monkeypatch.setattr(repo, "_sync_directory", sync_directory)
    repo.save_policy(updated)
    assert synced == [policy_path.parent]
    assert "Failed to sync governance policy directory" in caplog.text
    assert json.loads(policy_path.read_text()) == updated



def test_fallback_trim_syncs_directory_after_replace(tmp_path, monkeypatch):
    """Sync the replacement directory entry after trimming in fallback mode."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_bytes(b'{"new_version":"first"}\n{"new_version":"second"}\n')
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=1,
        has_atomic_io=False,
    )
    synced_contents = []

    def sync_directory(directory):
        assert directory == history_path.parent
        synced_contents.append(history_path.read_bytes())

    monkeypatch.setattr(repo, "_sync_directory", sync_directory)
    repo.trim_policy_history()

    assert synced_contents == [b'{"new_version":"second"}\n']


def test_fallback_history_trim_preserves_existing_temp_named_file(tmp_path, monkeypatch):
    """The history replacement owns its temporary file."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_bytes(b'{"new_version":"first"}\n{"new_version":"second"}\n')
    sibling = tmp_path / "history.jsonl.tmp"
    sibling.write_bytes(b"existing data")
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=1,
        has_atomic_io=False,
    )

    def reject_full_read(*args, **kwargs):
        pytest.fail("History trim must not read the whole file at once")

    with monkeypatch.context() as patcher:
        patcher.setattr(type(history_path), "read_bytes", reject_full_read)
        repo.trim_policy_history()

    assert sibling.read_bytes() == b"existing data"
    assert repo.list_policy_history(limit=10, max_records=10) == [{"new_version": "second"}]
    assert not list(tmp_path.glob(".history.jsonl.*.tmp"))


@pytest.mark.parametrize("has_atomic_io", [True, False])
def test_history_trim_preserves_appended_events_on_replace_failure(
    tmp_path, monkeypatch, has_atomic_io
):
    """A failed trim leaves the original history available for a later retry."""
    import os

    history_path = tmp_path / "history.jsonl"
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=1,
        has_atomic_io=has_atomic_io,
    )
    first = {"version": "first"}
    second = {"version": "second"}
    repo.update_policy(previous={}, updated=first, proposer="operator", approvers=[], event_type="update")
    real_replace = os.replace

    def fail_history_replace(source, target):
        if target == history_path:
            raise OSError("history replacement failed")
        return real_replace(source, target)

    with monkeypatch.context() as patcher:
        patcher.setattr(os, "replace", fail_history_replace)
        repo.update_policy(previous=first, updated=second, proposer="operator", approvers=[], event_type="update")

    assert len(history_path.read_text(encoding="utf-8").splitlines()) == 2
    assert not list(tmp_path.glob("*history*.tmp"))
    repo.trim_policy_history()
    assert [record["new_version"] for record in repo.list_policy_history(
        limit=10, max_records=10
    )] == ["second"]


@pytest.mark.parametrize("terminator", [b"", b"\n"])
def test_history_read_handles_records_spanning_blocks(tmp_path, monkeypatch, terminator):
    """Return the newest valid records even when lines span read blocks."""
    monkeypatch.setattr(
        "veritas_os.governance.file_repository._HISTORY_READ_BLOCK_SIZE", 7
    )
    history_path = tmp_path / "history.jsonl"
    history_path.write_bytes(
        '{"new_version":"古い"}\n'.encode()
        + b'{"new_version":"second"}\n{\n{"new_version":"third"}'
        + terminator
    )
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=10,
    )

    assert [record["new_version"] for record in repo.list_policy_history(
        limit=2, max_records=10
    )] == ["third", "second"]
    assert [record["new_version"] for record in repo.list_policy_history(
        limit=10, max_records=10
    )] == ["third", "second", "古い"]


def test_history_read_stops_after_requested_valid_records(tmp_path, monkeypatch, caplog):
    """The latest valid record can be returned without scanning older blocks."""
    block_size = 64
    monkeypatch.setattr(
        "veritas_os.governance.file_repository._HISTORY_READ_BLOCK_SIZE", block_size
    )
    history_path = tmp_path / "history.jsonl"
    newest = b'{"new_version":"latest"}\n{\n'
    payload = b'{"new_version":"older"}\n' * 100 + newest
    reads = []

    class TrackedHistory(BytesIO):
        def read(self, size=-1):
            reads.append((self.tell(), size))
            return super().read(size)

    real_open = Path.open

    def open_history(path, *args, **kwargs):
        if path == history_path:
            return TrackedHistory(payload)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_history)
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=10,
    )

    assert repo.list_policy_history(limit=1, max_records=10) == [{"new_version": "latest"}]
    assert reads == [(len(payload) - block_size, block_size)]
    assert "Skipped 1 invalid governance policy history record" in caplog.text


@pytest.mark.parametrize("history_max", [2, 10])
@pytest.mark.parametrize("fragment", [b'{"new_version":', b'{"new_version":"\xe3\x81'])
def test_history_append_isolates_incomplete_record(tmp_path, history_max, fragment, caplog):
    """A torn record cannot hide complete events on either side of it."""
    history_path = tmp_path / "history.jsonl"
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=history_max,
    )
    first = {"version": "first"}
    second = {"version": "second"}
    repo.update_policy(previous={}, updated=first, proposer="operator",
                       approvers=[], event_type="update")
    with history_path.open("ab") as history:
        history.write(fragment)
    repo.update_policy(previous=first, updated=second, proposer="operator",
                       approvers=[], event_type="update")

    records = repo.list_policy_history(limit=10, max_records=10)
    assert [record["new_version"] for record in records] == ["second", "first"]
    operation = "trim" if history_max == 2 else "read"
    assert [
        record.getMessage()
        for record in caplog.records
        if "invalid governance policy history record" in record.getMessage()
    ] == [f"Skipped 1 invalid governance policy history record(s) during {operation}"]
    if history_max == 2:
        assert len(history_path.read_bytes().splitlines()) == 2


@pytest.mark.parametrize("history_max", [2, 10])
def test_history_skips_json_conversion_errors(tmp_path, monkeypatch, history_max):
    """One decoder failure must preserve the neighboring records."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        '{"new_version":"first"}\n{"new_version":"invalid"}\n{"new_version":"last"}\n',
        encoding="utf-8",
    )
    repo = FileGovernanceRepository(
        policy_path=tmp_path / "policy.json",
        history_path=history_path,
        lock=threading.Lock(),
        policy_history_max=history_max,
    )
    loads = json.loads

    def decode(line, *args, **kwargs):
        if line == '{"new_version":"invalid"}':
            raise ValueError("JSON integer conversion limit exceeded")
        return loads(line, *args, **kwargs)

    monkeypatch.setattr(json, "loads", decode)
    repo.trim_policy_history()
    records = repo.list_policy_history(limit=10, max_records=10)

    assert [record["new_version"] for record in records] == ["last", "first"]
    assert len(history_path.read_bytes().splitlines()) == min(history_max, 3)


@pytest.mark.parametrize("content", [b"{", b"null", b"[]", b"\xff", None])
def test_file_repository_refuses_unreadable_saved_policy(tmp_path, content):
    """Defaults apply to missing policy files only."""
    policy_path = tmp_path / "governance.json"
    repo = FileGovernanceRepository(
        policy_path=policy_path,
        history_path=tmp_path / "governance_history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
    )
    if content is None:
        policy_path.mkdir()
    else:
        policy_path.write_bytes(content)

    def unexpected_default():
        pytest.fail("Unreadable saved policy was replaced by defaults")

    with pytest.raises(RuntimeError, match="governance policy"):
        repo.get_current_policy(default_factory=unexpected_default)


class _InMemoryRepository:
    def __init__(self) -> None:
        self.policy = gov.GovernancePolicy().model_dump()
        self.history: list[dict] = []

    def get_current_policy(self, *, default_factory):
        return self.policy or default_factory()

    def save_policy(self, policy):
        self.policy = policy

    def append_policy_event(self, event):
        self.history.append(event.to_dict())

    def list_policy_history(self, *, limit, max_records):
        return list(reversed(self.history))[: max(1, min(limit, max_records))]

    def update_policy(
        self,
        *,
        previous,
        updated,
        proposer,
        approvers,
        event_type,
        approval_records=None,
        reason="",
    ):
        del approval_records, reason
        self.policy = updated
        self.history.append(
            {
                "previous_policy": previous,
                "new_policy": updated,
                "proposer": proposer,
                "approvers": approvers,
                "event_type": event_type,
            }
        )

    def rollback_policy(
        self,
        *,
        previous,
        restored,
        proposer,
        approvers,
        approval_records=None,
        reason="",
    ):
        del approval_records, reason
        self.policy = restored
        self.history.append(
            {
                "previous_policy": previous,
                "new_policy": restored,
                "proposer": proposer,
                "approvers": approvers,
                "event_type": "rollback",
            }
        )


def test_governance_api_uses_repository_interface(monkeypatch):
    """API-level operations should flow through repository interface methods."""
    repo = _InMemoryRepository()
    gov.set_governance_repository_factory(lambda: repo)
    monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")

    updated = gov.update_policy({"version": "governance_v2", "updated_by": "alice"})
    assert updated["version"] == "governance_v2"

    history = gov.get_policy_history(limit=5)
    assert history[0]["event_type"] == "update"

    rolled_back = gov.rollback_policy(
        {**repo.policy, "version": "governance_v1_restored"},
        rolled_back_by="bob",
        approvals=[
            {"reviewer": "r1", "signature": "s1"},
            {"reviewer": "r2", "signature": "s2"},
        ],
    )
    assert rolled_back["version"] == "governance_v1_restored"

    latest_history = gov.get_policy_history(limit=1)
    assert latest_history[0]["event_type"] == "rollback"


def test_file_mode_behavior_unchanged_for_load_save(tmp_path, monkeypatch):
    """Backward-compatible helpers still read/write JSON file based policy."""
    policy_path = tmp_path / "governance.json"
    history_path = tmp_path / "governance_history.jsonl"
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "file")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
    monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)

    policy = gov.GovernancePolicy().model_dump()
    policy["version"] = "legacy-file-mode"
    gov._save(policy)

    loaded = gov._load()
    assert loaded["version"] == "legacy-file-mode"

    on_disk = json.loads(policy_path.read_text(encoding="utf-8"))
    assert on_disk["version"] == "legacy-file-mode"
