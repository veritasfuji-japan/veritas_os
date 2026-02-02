from pathlib import Path
import importlib
import os
import stat

import pytest

from veritas_os.logging import paths


def test_dataset_dir_is_path_and_exists(tmp_path, monkeypatch):
    """
    DATASET_DIR が Path で、VERITAS_DATA_DIR を変えると
    そっち側にぶら下がることを軽く確認するテスト。
    """

    # 環境変数を一時ディレクトリに差し替え
    monkeypatch.setenv("VERITAS_DATA_DIR", str(tmp_path))

    # env 変更を反映させるために再読み込み
    importlib.reload(paths)

    assert isinstance(paths.DATASET_DIR, Path)

    # DATASET_DIR が VERITAS_DATA_DIR 以下になっていることを期待
    assert str(paths.DATASET_DIR).startswith(str(tmp_path))

    # ディレクトリ自体は作成されているはず
    assert paths.DATASET_DIR.exists()


def test_require_encrypted_log_root_missing(monkeypatch):
    """暗号化ログ強制時に設定が無い場合は例外を出す。"""
    monkeypatch.delenv("VERITAS_ENCRYPTED_LOG_ROOT", raising=False)
    monkeypatch.setenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR", "1")

    with pytest.raises(RuntimeError):
        importlib.reload(paths)


def test_log_root_permissions(tmp_path, monkeypatch):
    """ログディレクトリの権限を700に揃える（Windows以外）。"""
    if os.name == "nt":
        return

    monkeypatch.setenv("VERITAS_LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.delenv("VERITAS_DATA_DIR", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTED_LOG_ROOT", raising=False)
    monkeypatch.delenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR", raising=False)

    module = importlib.reload(paths)
    log_mode = stat.S_IMODE(module.LOG_DIR.stat().st_mode)
    dash_mode = stat.S_IMODE(module.DASH_DIR.stat().st_mode)

    assert log_mode == 0o700
    assert dash_mode == 0o700
