from pathlib import Path
import importlib
import os

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

