import os
from pathlib import Path
from typing import TextIO, Union

from .paths import LOG_JSONL

MAX_LINES = 5000


def _get_trust_log_path() -> Path:
    """
    trust_log.jsonl のパスを取得する。
    テスト時のパッチを反映するため、毎回 paths からインポートする。
    """
    # paths モジュールから最新のパスを取得（テストでパッチされている可能性がある）
    from . import paths
    return paths.LOG_JSONL


def count_lines(path: Union[str, Path]) -> int:
    """ファイルの行数をカウントする（str/Path両対応）"""
    p = Path(path) if isinstance(path, str) else path
    if not p.exists():
        return 0
    with open(p, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def rotate_if_needed() -> Path:
    trust_log = _get_trust_log_path()
    lines = count_lines(trust_log)
    if lines < MAX_LINES:
        return trust_log

    # rotate
    base = str(trust_log).replace(".jsonl", "")
    rotated = Path(base + "_old.jsonl")
    if rotated.exists():
        rotated.unlink()
    trust_log.rename(rotated)

    return trust_log


def open_trust_log_for_append() -> TextIO:
    """
    trust_log.jsonl を追記モードで開く。
    必要に応じてローテーションを行う。
    """
    trust_log = rotate_if_needed()
    trust_log.parent.mkdir(parents=True, exist_ok=True)
    return open(trust_log, "a", encoding="utf-8")
