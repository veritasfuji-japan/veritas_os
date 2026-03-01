import logging
import os
from pathlib import Path
from typing import TextIO, Union

from .paths import LOG_JSONL

logger = logging.getLogger(__name__)

MAX_LINES = 5000

# ★ ローテーション時にハッシュチェーンの連続性を保つためのマーカーファイル
# 最終ハッシュ値を保存し、新しいファイルの最初のエントリで参照する
_LAST_HASH_MARKER = ".last_hash"
_READ_CHUNK_SIZE = 65536


def _get_trust_log_path() -> Path:
    """
    trust_log.jsonl のパスを取得する。
    テスト時のパッチを反映するため、毎回 paths からインポートする。
    """
    # paths モジュールから最新のパスを取得（テストでパッチされている可能性がある）
    from . import paths
    return paths.LOG_JSONL


def _get_last_hash_marker_path(trust_log: Path) -> Path:
    """ローテーション用マーカーファイルのパスを返す"""
    return trust_log.parent / _LAST_HASH_MARKER


def _read_last_nonempty_line(path: Path) -> str | None:
    """大きなログでも末尾の非空行を安全に取得する。"""
    if not path.exists():
        return None

    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        if file_size == 0:
            return None

        pos = file_size
        buf = b""
        newline_count = 0

        while pos > 0:
            read_size = min(_READ_CHUNK_SIZE, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            if not chunk:
                break

            buf = chunk + buf
            newline_count += chunk.count(b"\n")

            # 末尾行の直前に改行が見つかれば、これ以上読み戻さなくてよい。
            if newline_count >= 2 or (newline_count >= 1 and not buf.endswith(b"\n")):
                break

    for raw_line in reversed(buf.splitlines()):
        if raw_line.strip():
            return raw_line.decode("utf-8", errors="replace")
    return None


def save_last_hash_marker(trust_log: Path) -> None:
    """ローテーション前に最終ハッシュ値をマーカーファイルに保存する。

    ★ ハッシュチェーン連続性: ローテーション後の新しいファイルで
    チェーンを継続できるよう、最終ハッシュを保存する。
    """
    import json as _json

    marker = _get_last_hash_marker_path(trust_log)
    try:
        if not trust_log.exists():
            return
        last_line = _read_last_nonempty_line(trust_log)
        if not last_line:
            return
        last = _json.loads(last_line)
        last_hash = last.get("sha256")
        if last_hash:
            marker.write_text(last_hash, encoding="utf-8")
    except Exception:
        logger.debug("save_last_hash_marker failed for %s", trust_log, exc_info=True)


def load_last_hash_marker(trust_log: Path) -> "str | None":
    """マーカーファイルから最終ハッシュ値を読み込む。

    ★ ハッシュチェーン連続性: ローテーション後に新しいファイルが空の場合、
    マーカーから前ファイルの最終ハッシュを取得してチェーンを継続する。
    """
    marker = _get_last_hash_marker_path(trust_log)
    try:
        if marker.exists():
            val = marker.read_text(encoding="utf-8").strip()
            return val if val else None
    except Exception:
        logger.debug("load_last_hash_marker failed for %s", trust_log, exc_info=True)
    return None


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

    # ★ ハッシュチェーン連続性: ローテーション前に最終ハッシュを保存
    save_last_hash_marker(trust_log)

    # rotate - use Path methods for safe suffix handling
    # Using trust_log.stem ensures only the file suffix is removed, not all occurrences
    rotated = trust_log.parent / (trust_log.stem + "_old.jsonl")
    # ★ セキュリティ修正: シンボリックリンク攻撃を防止
    if trust_log.is_symlink():
        raise RuntimeError("Refusing to rotate: symlink detected on log paths")
    # ★ セキュリティ: 解決済みパスがログディレクトリ内にあることを確認
    resolved_parent = trust_log.parent.resolve()
    if trust_log.resolve().parent != resolved_parent:
        raise RuntimeError("Refusing to rotate: resolved path outside log directory")

    # 既存の rotated が通常ファイル/シンボリックリンクであっても、
    # os.replace() は名前エントリをアトミックに置換するため
    # is_symlink()->unlink() の TOCTOU 競合を避けられる。
    os.replace(trust_log, rotated)

    return trust_log


def open_trust_log_for_append() -> TextIO:
    """
    trust_log.jsonl を追記モードで開く。
    必要に応じてローテーションを行う。
    
    ★ 修正 (H-7): rotate_if_needed() と open() の間に他のスレッドが
      ローテーションを実行するリスクを文書化。
      呼び出し側で _trust_log_lock を保持することで、アトミック性を保証する。
    
    注意: この関数は trust_log.py の _trust_log_lock 内で呼ばれることを想定。
          単独で呼び出す場合は、ローテーションと open の間の競合に注意。
    """
    trust_log = rotate_if_needed()
    trust_log.parent.mkdir(parents=True, exist_ok=True)
    return open(trust_log, "a", encoding="utf-8")
