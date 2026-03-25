"""Tests for ``veritas_os.core.memory_storage``."""

from __future__ import annotations

from pathlib import Path

import pytest

import veritas_os.core.memory_storage as memory_storage


class TestLockedMemoryPosix:
    def test_basic_lock_unlock(self, tmp_path: Path) -> None:
        target = tmp_path / "memory.json"
        target.write_text("[]", encoding="utf-8")

        with memory_storage.locked_memory(target):
            assert target.exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "dir" / "memory.json"

        with memory_storage.locked_memory(target):
            pass

        assert target.parent.exists()

    @pytest.mark.skipif(
        memory_storage.fcntl is None or memory_storage.IS_WIN,
        reason="POSIX flock branch only",
    )
    def test_unlock_failure_logs_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        target = tmp_path / "memory.json"

        original_flock = memory_storage.fcntl.flock

        def flaky_unlock(fd: int, operation: int) -> None:
            if operation == memory_storage.fcntl.LOCK_UN:
                raise OSError("unlock boom")
            original_flock(fd, operation)

        monkeypatch.setattr(memory_storage.fcntl, "flock", flaky_unlock)

        with caplog.at_level("ERROR"):
            with memory_storage.locked_memory(target):
                pass

        assert "unlock failed" in caplog.text


class TestLockedMemoryFallback:
    def test_fallback_acquires_and_cleans_lockfile(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "memory.json"
        lock_path = target.with_suffix(".json.lock")
        monkeypatch.setattr(memory_storage, "fcntl", None)

        with memory_storage.locked_memory(target):
            assert lock_path.exists()

        assert not lock_path.exists()

    def test_removes_stale_lockfile(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        target = tmp_path / "memory.json"
        lock_path = target.with_suffix(".json.lock")
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("stale", encoding="utf-8")

        monkeypatch.setattr(memory_storage, "fcntl", None)

        now = 10_000.0

        def fake_time() -> float:
            return now

        def fake_getmtime(_: str) -> float:
            return now - 301.0

        monkeypatch.setattr(memory_storage.time, "time", fake_time)
        monkeypatch.setattr(memory_storage.os.path, "getmtime", fake_getmtime)

        with caplog.at_level("WARNING"):
            with memory_storage.locked_memory(target):
                pass

        assert "Removing stale lockfile" in caplog.text
        assert not lock_path.exists()

    def test_mtime_check_failure_debug_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        target = tmp_path / "memory.json"
        lock_path = target.with_suffix(".json.lock")
        lock_path.write_text("occupied", encoding="utf-8")

        monkeypatch.setattr(memory_storage, "fcntl", None)

        real_open = memory_storage.os.open

        def fake_open(path: str, flags: int, mode: int = 0o777) -> int:
            if path == str(lock_path):
                raise FileExistsError
            return real_open(path, flags, mode)

        monkeypatch.setattr(memory_storage.os, "open", fake_open)
        monkeypatch.setattr(
            memory_storage.os.path,
            "getmtime",
            lambda _path: (_ for _ in ()).throw(OSError("mtime failed")),
        )

        clock = {"t": 0.0}

        def fake_time() -> float:
            clock["t"] += 0.3
            return clock["t"]

        monkeypatch.setattr(memory_storage.time, "time", fake_time)
        monkeypatch.setattr(memory_storage.time, "sleep", lambda _: None)

        with caplog.at_level("DEBUG"):
            with pytest.raises(TimeoutError):
                with memory_storage.locked_memory(target, timeout=0.5):
                    pass

        assert "mtime check failed" in caplog.text

    def test_timeout_when_lock_never_released(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target = tmp_path / "memory.json"
        lock_path = target.with_suffix(".json.lock")
        lock_path.write_text("busy", encoding="utf-8")

        monkeypatch.setattr(memory_storage, "fcntl", None)
        monkeypatch.setattr(memory_storage.os.path, "getmtime", lambda _: 0.0)
        monkeypatch.setattr(memory_storage.time, "sleep", lambda _: None)

        times = iter([0.0, 0.3, 0.7])
        monkeypatch.setattr(memory_storage.time, "time", lambda: next(times))

        with pytest.raises(TimeoutError):
            with memory_storage.locked_memory(target, timeout=0.5):
                pass

    def test_cleanup_failure_logs_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        target = tmp_path / "memory.json"
        lock_path = target.with_suffix(".json.lock")
        monkeypatch.setattr(memory_storage, "fcntl", None)

        original_unlink = Path.unlink

        def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
            if self == lock_path:
                raise OSError("cleanup failed")
            original_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", flaky_unlink)

        with caplog.at_level("ERROR"):
            with memory_storage.locked_memory(target):
                pass

        assert "lockfile cleanup failed" in caplog.text


class TestLegacyPickleGuards:
    def test_warn_for_pickle_extensions_and_nested_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = tmp_path / "nested"
        nested.mkdir(parents=True)
        (nested / "a.pkl").write_bytes(b"pkl")
        (nested / "b.joblib").write_bytes(b"joblib")
        (nested / "c.pickle").write_bytes(b"pickle")
        (nested / "ignore.json").write_text("{}", encoding="utf-8")

        calls: list[tuple[Path, str]] = []

        def fake_emit(path: Path, artifact_name: str) -> None:
            calls.append((path, artifact_name))

        monkeypatch.setattr(
            memory_storage,
            "_emit_legacy_pickle_runtime_blocked",
            fake_emit,
        )

        memory_storage._warn_for_legacy_pickle_artifacts([tmp_path])

        assert sorted(path.name for path, _ in calls) == [
            "a.pkl",
            "b.joblib",
            "c.pickle",
        ]
        assert all(name == "runtime artifact" for _, name in calls)

    def test_deduplicates_equivalent_roots(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (tmp_path / "artifact.pkl").write_bytes(b"data")
        calls: list[Path] = []

        monkeypatch.setattr(
            memory_storage,
            "_emit_legacy_pickle_runtime_blocked",
            lambda path, artifact_name: calls.append(path),
        )

        relative = tmp_path / "."
        memory_storage._warn_for_legacy_pickle_artifacts([tmp_path, relative])

        assert len(calls) == 1

    def test_ignores_missing_and_non_directory_roots(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        missing = tmp_path / "missing"
        file_root = tmp_path / "not_dir"
        file_root.write_text("x", encoding="utf-8")

        called = False

        def fake_emit(path: Path, artifact_name: str) -> None:
            nonlocal called
            called = True

        monkeypatch.setattr(
            memory_storage,
            "_emit_legacy_pickle_runtime_blocked",
            fake_emit,
        )

        memory_storage._warn_for_legacy_pickle_artifacts([missing, file_root])

        assert called is False

    def test_emit_legacy_pickle_runtime_blocked_logs_expected_message(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = Path("/tmp/legacy.pkl")

        with caplog.at_level("ERROR"):
            memory_storage._emit_legacy_pickle_runtime_blocked(path, "index")

        assert "Runtime pickle/joblib loading is permanently disabled" in caplog.text
        assert str(path) in caplog.text
