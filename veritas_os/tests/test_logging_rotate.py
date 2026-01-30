# veritas_os/tests/test_logging_rotate.py
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from veritas_os.logging import rotate
import veritas_os.logging.paths as log_paths


def _setup_tmp_trust_log(tmp_path, monkeypatch, max_lines=3):
    """
    rotate モジュールが扱う paths.LOG_JSONL / MAX_LINES を
    tmp_path 配下に切り替えるヘルパ。
    """
    log_path = tmp_path / "trust_log.jsonl"
    # paths モジュールのパスをパッチ
    monkeypatch.setattr(log_paths, "LOG_JSONL", log_path)
    monkeypatch.setattr(rotate, "MAX_LINES", max_lines, raising=False)
    return log_path


def test_count_lines_basic(tmp_path):
    # 存在しないファイル → 0 行
    missing = tmp_path / "no_such_file.jsonl"
    assert rotate.count_lines(str(missing)) == 0

    # 存在するファイル → 行数を正しくカウント
    p = tmp_path / "sample.jsonl"
    p.write_text("a\nb\nc\n", encoding="utf-8")
    assert rotate.count_lines(str(p)) == 3


def test_rotate_if_needed_no_rotation_when_below_max(tmp_path, monkeypatch):
    """
    行数が MAX_LINES 未満のときはローテーションしない。
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch, max_lines=5)

    # 3 行だけ書く（5 未満）
    log_path.write_text("1\n2\n3\n", encoding="utf-8")

    returned = rotate.rotate_if_needed()

    # パスは LOG_JSONL のまま（Pathオブジェクト）
    assert returned == log_path
    # ファイルも消えていない
    assert log_path.exists()
    assert rotate.count_lines(log_path) == 3

    # _old ファイルは作られていない
    old_path = tmp_path / "trust_log_old.jsonl"
    assert not old_path.exists()


def test_rotate_if_needed_rotates_and_overwrites_old(tmp_path, monkeypatch):
    """
    行数が MAX_LINES 以上のとき:
    - trust_log.jsonl → trust_log_old.jsonl にローテート
    - すでに old がある場合は削除してから上書き
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch, max_lines=3)
    old_path = tmp_path / "trust_log_old.jsonl"

    # 1 回目: old が存在しない状態でローテーション
    log_path.write_text("a\nb\nc\n", encoding="utf-8")  # 3 行 = MAX_LINES
    returned1 = rotate.rotate_if_needed()
    assert returned1 == log_path

    # trust_log はリネームされて存在しない
    assert not log_path.exists()
    # old が生成されている
    assert old_path.exists()
    assert rotate.count_lines(old_path) == 3

    # 2 回目: 既に old がある状態で再度ローテーション
    # 新しい trust_log を作り直して 4 行書く
    log_path.write_text("1\n2\n3\n4\n", encoding="utf-8")
    returned2 = rotate.rotate_if_needed()
    assert returned2 == log_path

    # 再び trust_log はリネームされて消える
    assert not log_path.exists()
    # old は上書きされて 4 行になっている
    assert old_path.exists()
    assert rotate.count_lines(old_path) == 4


def test_open_trust_log_for_append_creates_file_and_appends(tmp_path, monkeypatch):
    """
    open_trust_log_for_append:
    - rotate_if_needed が呼ばれる
    - 存在しない場合は新規作成
    - append モードで追記できる
    """
    log_path = _setup_tmp_trust_log(tmp_path, monkeypatch, max_lines=100)

    # まだファイルは存在しない
    assert not log_path.exists()

    # 1 回目の append → ファイル作成 & 1 行
    with rotate.open_trust_log_for_append() as f:
        f.write("first\n")

    assert log_path.exists()
    assert rotate.count_lines(log_path) == 1

    # 2 回目の append → さらに 1 行追加
    with rotate.open_trust_log_for_append() as f:
        f.write("second\n")

    assert rotate.count_lines(log_path) == 2
