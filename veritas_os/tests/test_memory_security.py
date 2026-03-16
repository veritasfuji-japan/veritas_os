from pathlib import Path

from veritas_os.core import memory_security


def test_is_explicitly_enabled_truthy_and_falsey(monkeypatch):
    monkeypatch.delenv("VERITAS_TEST_FLAG", raising=False)
    assert memory_security.is_explicitly_enabled("VERITAS_TEST_FLAG") is False

    monkeypatch.setenv("VERITAS_TEST_FLAG", "true")
    assert memory_security.is_explicitly_enabled("VERITAS_TEST_FLAG") is True

    monkeypatch.setenv("VERITAS_TEST_FLAG", "0")
    assert memory_security.is_explicitly_enabled("VERITAS_TEST_FLAG") is False


def test_warn_for_legacy_pickle_artifacts_emits_security_log(
    tmp_path: Path,
    monkeypatch,
):
    blocked = []

    def _record(path: Path, artifact_name: str) -> None:
        blocked.append((path.name, artifact_name))

    monkeypatch.setattr(
        memory_security,
        "emit_legacy_pickle_runtime_blocked",
        _record,
    )

    (tmp_path / "ok.json").write_text("{}", encoding="utf-8")
    (tmp_path / "legacy.pkl").write_text("x", encoding="utf-8")
    (tmp_path / "legacy.joblib").write_text("x", encoding="utf-8")

    memory_security.warn_for_legacy_pickle_artifacts([tmp_path, tmp_path])

    assert sorted(blocked) == [
        ("legacy.joblib", "runtime artifact"),
        ("legacy.pkl", "runtime artifact"),
    ]
