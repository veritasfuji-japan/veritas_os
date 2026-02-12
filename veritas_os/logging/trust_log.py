# veritas_os/logging/trust_log.py
# 正規TrustLog実装: 論文の式 hₜ = SHA256(hₜ₋₁ || rₜ) に完全準拠
#
# このモジュールがVERITASの唯一のTrustLog実装です。
# 他のモジュールはここをインポートして使用してください。
#
# 機能:
# - append_trust_log: ハッシュチェーン付きでエントリを追記
# - iter_trust_log: ログをイテレート
# - load_trust_log: 最近のエントリをまとめて取得
# - get_trust_log_entry: request_id で単一エントリを取得
# - verify_trust_log: ハッシュチェーンの整合性を検証
# - iso_now: 監査用 UTC ISO8601 時刻
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from veritas_os.logging.paths import LOG_DIR
from veritas_os.logging.rotate import open_trust_log_for_append, load_last_hash_marker
from veritas_os.core.atomic_io import atomic_write_json, atomic_append_line

try:
    from veritas_os.core.sanitize import mask_pii as _mask_pii
except Exception as _import_err:  # pragma: no cover
    _mask_pii = None  # type: ignore[assignment]
    logging.getLogger(__name__).warning(
        "sanitize.mask_pii unavailable; shadow log PII masking disabled: %s",
        _import_err,
    )

logger = logging.getLogger(__name__)

# trust_log の JSON/JSONL は LOG_DIR 直下に置く
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# trust_log.json に保持する最大件数
MAX_JSON_ITEMS = 2000

# スレッドセーフ化: ハッシュチェーンの整合性を保証するためのロック
# ★ マルチスレッド環境（FastAPI等）での同時書き込みによるチェーン破損を防止
# NOTE: server.py のフォールバック trust log もこのロックを共有する
_trust_log_lock = threading.RLock()
trust_log_lock = _trust_log_lock  # 公開 API（server.py 等から参照用）


# =============================================================================
# ヘルパー関数
# =============================================================================

def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: Any) -> str:
    """UTF-8 / bytes から SHA-256 ハッシュを生成"""
    if isinstance(data, bytes):
        raw = data
    else:
        raw = str(data).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_entry_for_hash(entry: Dict[str, Any]) -> str:
    """
    sha256 計算用にエントリを正規化:
    - sha256 / sha256_prev フィールドは除外
    - sort_keys=True で JSON 化して順序を固定
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _compute_sha256(payload: dict) -> str:
    """
    entry 用の SHA-256 ハッシュを計算する。
    - dict を key でソートして JSON 化
    - それを UTF-8 でエンコードして sha256 に通す
    """
    try:
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except Exception:
        logger.debug("_compute_sha256: JSON serialization failed, using default=str fallback", exc_info=True)
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def get_last_hash() -> str | None:
    """直近の trust_log.jsonl から最後の SHA-256 値を取得。

    ファイル末尾からシークして最終行のみを読み込む。
    全行をメモリに読み込まないため、大きなファイルでもメモリ効率が良い。

    ★ ハッシュチェーン連続性: JSONL が空の場合（ローテーション直後）は
      マーカーファイルからローテーション前の最終ハッシュを取得する。

    ★ 修正 (H-12): _trust_log_lock を取得してスレッドセーフにする。
      外部から直接呼ばれた場合でも、書き込み中の不完全な行を
      読み込むリスクを排除する。
    """
    with _trust_log_lock:
        try:
            if not LOG_JSONL.exists():
                # ★ ローテーション後: マーカーから前ファイルの最終ハッシュを取得
                return load_last_hash_marker(LOG_JSONL)
            file_size = LOG_JSONL.stat().st_size
            if file_size == 0:
                # ★ ローテーション後: マーカーから前ファイルの最終ハッシュを取得
                return load_last_hash_marker(LOG_JSONL)
            with open(LOG_JSONL, "rb") as f:
                # ★ H-6 修正: バッファを 64KB に拡大（大きなエントリに対応）
                chunk_size = min(65536, file_size)
                f.seek(file_size - chunk_size)
                raw = f.read()
                # ★ UTF-8 境界安全: seek がマルチバイト文字の途中に
                # 当たる可能性があるため errors="replace" で安全にデコード。
                # 置換文字は先頭の不完全行にのみ影響し、lines[-1] は
                # 常に EOF まで読み込んだ完全な行なので安全。
                chunk = raw.decode("utf-8", errors="replace")
                lines = chunk.strip().split("\n")
                if lines:
                    last = json.loads(lines[-1])
                    return last.get("sha256")
        except Exception as exc:
            logger.warning("get_last_hash failed: %s", exc)
        return None


def calc_sha256(payload: dict) -> str:
    """entry の SHA-256 ハッシュを計算する（外部用の薄いヘルパー）

    NOTE: ensure_ascii=False を使用してハッシュチェーンの
    append_trust_log / verify_trust_log と整合性を保つ。
    """
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_logs_json() -> list:
    """
    trust_log.json から items(list[dict]) を安全に読み込む。
    変な値（int, str など）が混ざっていても捨てる。
    """
    try:
        with open(LOG_JSON, "r", encoding="utf-8") as f:
            obj = json.load(f)

        if isinstance(obj, dict):
            items = obj.get("items", [])
        elif isinstance(obj, list):
            items = obj
        else:
            items = []

        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]
    except FileNotFoundError:
        return []
    except Exception:
        logger.warning("_load_logs_json: failed to load %s", LOG_JSON, exc_info=True)
        return []


def _save_json(items: list) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(LOG_JSON, {"items": items}, indent=2)


def append_trust_log(entry: dict) -> Dict[str, Any]:
    """
    決定ごとの監査ログ（軽量）を JSONL + JSON に保存。

    論文の式に従った実装:
        hₜ = SHA256(hₜ₋₁ || rₜ)

    where:
        hₜ₋₁ = 直前のハッシュ値 (sha256_prev)
        rₜ   = 現在のエントリ (JSON化、sha256とsha256_prevを除外)
        ||   = 文字列連結
        hₜ   = 現在のハッシュ値 (sha256)

    実装詳細:
        1. 直前のハッシュ値 (sha256_prev) を取得
        2. 現在のエントリに sha256_prev をセット
        3. エントリから sha256 と sha256_prev を除外してJSON化 (rₜ)
        4. sha256_prev + rₜ を連結
        5. SHA-256ハッシュを計算して sha256 にセット
        6. JSONLとJSONファイルに保存

    - JSONL は 5000 行でローテーション（rotate.py 側）
    - trust_log.json は最新 MAX_JSON_ITEMS 件だけ保持

    ★ スレッドセーフ: RLock で全操作を保護（ハッシュチェーンの整合性保証）

    Returns:
        sha256, sha256_prev が付与されたエントリ（渡された entry も更新される）
    """
    import os

    # ★ スレッドセーフ: ハッシュチェーンの整合性を保証するためロックを取得
    with _trust_log_lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # ---- 直前ハッシュの取得（JSONL 側を正とする）----
        # ★ 修正: JSON (MAX_JSON_ITEMS 件に制限) ではなく JSONL (全件) から
        #   直前ハッシュを取得する。JSON が 2000 件で切られている場合、
        #   JSON の末尾と JSONL の末尾が乖離してチェーンが壊れる問題を修正。
        sha256_prev = get_last_hash()

        items = _load_logs_json()

        # 元 entry を壊さないようにコピー
        entry = dict(entry)
        entry.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        entry["sha256_prev"] = sha256_prev

        # ✅ 論文の式に準拠: hₜ = SHA256(hₜ₋₁ || rₜ)
        # エントリから sha256 と sha256_prev を除外（これが rₜ）
        hash_payload = dict(entry)
        hash_payload.pop("sha256", None)
        hash_payload.pop("sha256_prev", None)  # ⚠️ 重要: sha256_prev をハッシュ計算から除外

        # rₜ を JSON化（キーをソートして一意性を保証）
        entry_json = json.dumps(hash_payload, sort_keys=True, ensure_ascii=False)

        # hₜ₋₁ || rₜ を結合
        if sha256_prev:
            combined = sha256_prev + entry_json
        else:
            # 最初のエントリの場合は rₜ のみ
            combined = entry_json

        # SHA-256計算: hₜ = SHA256(hₜ₋₁ || rₜ)
        entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

        # ---- JSONL に1行追記 (with fsync for durability) ----
        with open_trust_log_for_append() as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        # ---- JSON(配列) を更新（最新 N 件だけ残す）----
        items.append(entry)
        if len(items) > MAX_JSON_ITEMS:
            items = items[-MAX_JSON_ITEMS:]

        _save_json(items)

        return entry


def write_shadow_decide(
    request_id: str,
    body: dict,
    chosen: dict,
    telos_score: float,
    fuji: dict,
) -> None:
    """
    Doctor / ダッシュボード用の 1-decide スナップショット
    """
    shadow_dir = LOG_DIR / "DASH"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    # タイムゾーン付きの UTC 時刻を使用（utcnow() は非推奨）
    now_utc = datetime.now(timezone.utc)

    # ファイル名用タイムスタンプ（ミリ秒まで）
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = shadow_dir / f"decide_{ts_str}.json"

    fuji_safe = fuji if isinstance(fuji, dict) else {}

    raw_query = (
        body.get("query")
        or (body.get("context") or {}).get("query")
        or ""
    )
    # ★ セキュリティ: シャドウログに書き出す前にPIIをマスク
    query = _mask_pii(raw_query) if _mask_pii and raw_query else raw_query

    rec = {
        "request_id": request_id,
        # ISO8601 + "Z"（UTC）に正規化
        "created_at": now_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "query": query,
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": fuji_safe.get("status"),
    }

    atomic_write_json(out, rec, indent=2)


# =============================================================================
# TrustLog 読み出し系
# =============================================================================

def iter_trust_log(reverse: bool = False) -> Iterable[Dict[str, Any]]:
    """
    TrustLog を1行ずつイテレートするジェネレータ

    Args:
        reverse: True の場合、末尾から逆順に返す

    Yields:
        dict: 個々のログエントリ

    ★ スレッドセーフ: reverse=True の場合、ファイル読み込みをロック下で行い、
      書き込み中の不完全な行を読み込むリスクを排除する。
    """
    if not LOG_JSONL.exists():
        return

    try:
        if reverse:
            # ★ 修正: _trust_log_lock 下でファイルを一括読み込み
            # concurrent な append_trust_log() が途中行を書き込んでいても
            # ロック取得後に完全なデータを読める
            with _trust_log_lock:
                with LOG_JSONL.open("rb") as f:
                    lines = f.readlines()
            for line in reversed(lines):
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    yield json.loads(line_str)
                except json.JSONDecodeError:
                    continue
        else:
            # ★ Bug fix: forward iteration もロック下でファイルを一括読み込み。
            # concurrent な append_trust_log() が途中行を書き込んでいても
            # ロック取得後に完全なデータを読める。
            with _trust_log_lock:
                with LOG_JSONL.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning("trust_log iterate failed: %s", e)
        return


def load_trust_log(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    TrustLog をまとめて読み込むユーティリティ

    Args:
        limit: 最大件数（None の場合は全件）

    Returns:
        list[dict]: 新しい順のエントリリスト
    """
    entries: List[Dict[str, Any]] = list(iter_trust_log(reverse=True))
    if limit is not None:
        entries = entries[:limit]
    return entries


def get_trust_log_entry(request_id: str) -> Optional[Dict[str, Any]]:
    """
    指定 request_id の TrustLog エントリを取得（末尾から検索）

    Args:
        request_id: /v1/decide の request_id

    Returns:
        dict | None: 対応するエントリ or 見つからない場合 None
    """
    if not request_id:
        return None

    for entry in iter_trust_log(reverse=True):
        if entry.get("request_id") == request_id:
            return entry
    return None


def _coerce_pagination(cursor: Optional[str], limit: int, *, max_limit: int = 200) -> tuple[int, int]:
    """TrustLog API のページング引数を正規化する。

    Args:
        cursor: オフセットを表す文字列。未指定時は 0。
        limit: 取得件数。
        max_limit: 1 回の取得上限。

    Returns:
        tuple[int, int]: ``(offset, safe_limit)``
    """
    safe_limit = max(1, min(int(limit), max_limit))
    if cursor is None or cursor == "":
        return 0, safe_limit

    try:
        offset = max(0, int(cursor))
    except (TypeError, ValueError):
        offset = 0
    return offset, safe_limit


def get_trust_log_page(cursor: Optional[str], limit: int) -> Dict[str, Any]:
    """最新→過去の順で TrustLog をページング取得する。

    Notes:
        API は必ず cursor/limit で返却し、全件返却を回避する。
    """
    offset, safe_limit = _coerce_pagination(cursor, limit)
    entries = load_trust_log(limit=None)
    page_items = entries[offset: offset + safe_limit]
    next_offset = offset + len(page_items)
    has_more = next_offset < len(entries)

    return {
        "items": page_items,
        "cursor": str(offset),
        "next_cursor": str(next_offset) if has_more else None,
        "limit": safe_limit,
        "has_more": has_more,
    }


def get_trust_logs_by_request(request_id: str) -> Dict[str, Any]:
    """request_id 単位で TrustLog エントリを取得する。"""
    if not request_id:
        return {
            "request_id": request_id,
            "items": [],
            "count": 0,
            "chain_ok": False,
            "verification_result": "request_id is required",
        }

    matched = [
        entry
        for entry in iter_trust_log(reverse=False)
        if entry.get("request_id") == request_id
    ]

    chain_ok = True
    for index in range(1, len(matched)):
        if matched[index].get("sha256_prev") != matched[index - 1].get("sha256"):
            chain_ok = False
            break

    verification = "ok" if chain_ok else "broken"
    if not matched:
        verification = "not_found"

    return {
        "request_id": request_id,
        "items": matched,
        "count": len(matched),
        "chain_ok": chain_ok,
        "verification_result": verification,
    }


# =============================================================================
# TrustLog 検証
# =============================================================================

def verify_trust_log(max_entries: Optional[int] = None) -> Dict[str, Any]:
    """
    TrustLog 全体（または先頭から max_entries 件）について
    ハッシュチェーンの整合性を検証する。

    Returns:
        {
          "ok": bool,
          "checked": int,
          "broken": bool,
          "broken_index": int | None,
          "broken_reason": str | None,
        }
    """
    if not LOG_JSONL.exists():
        return {
            "ok": True,
            "checked": 0,
            "broken": False,
            "broken_index": None,
            "broken_reason": None,
        }

    prev_hash: Optional[str] = None
    checked = 0

    try:
        # ★ スレッドセーフ修正: ロック下でファイルを一括読み込み
        # concurrent な append_trust_log() による不完全な行の読み込みを防止
        with _trust_log_lock:
            with LOG_JSONL.open("r", encoding="utf-8") as f:
                all_lines = f.readlines()

        for idx, line in enumerate(all_lines):
            if max_entries is not None and idx >= max_entries:
                break

            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken": True,
                    "broken_index": idx,
                    "broken_reason": "json_decode_error",
                }

            # sha256_prev の整合性チェック
            actual_prev = entry.get("sha256_prev")
            if prev_hash is None:
                # 最初のエントリ: sha256_prev が None なら新規チェーン。
                # 非 None ならログローテーション後の継続チェーンであり正常。
                # いずれの場合も、以降のエントリは自身の sha256 から検証する。
                pass
            else:
                if actual_prev != prev_hash:
                    return {
                        "ok": False,
                        "checked": checked,
                        "broken": True,
                        "broken_index": idx,
                        "broken_reason": "sha256_prev_mismatch",
                    }

            # sha256 の再計算チェック
            # ★ ログローテーション後の最初のエントリでは prev_hash がまだ None だが、
            #   エントリ自身の sha256_prev にはローテーション前の最終ハッシュが入っている。
            #   ハッシュ再計算にはその値を使う必要がある。
            expected_prev = prev_hash if prev_hash is not None else actual_prev
            entry_json = _normalize_entry_for_hash(entry)
            if expected_prev:
                combined = expected_prev + entry_json
            else:
                combined = entry_json
            expected_hash = _sha256(combined)
            if entry.get("sha256") != expected_hash:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken": True,
                    "broken_index": idx,
                    "broken_reason": "sha256_mismatch",
                }

            # 状態更新
            prev_hash = entry.get("sha256")
            checked += 1

        return {
            "ok": True,
            "checked": checked,
            "broken": False,
            "broken_index": None,
            "broken_reason": None,
        }

    except Exception as e:
        logger.warning("verify_trust_log failed: %s", e)
        return {
            "ok": False,
            "checked": checked,
            "broken": True,
            "broken_index": checked,
            "broken_reason": "verification_exception",
        }


# =============================================================================
# 公開 API
# =============================================================================

__all__ = [
    "iso_now",
    "append_trust_log",
    "append_trust_event",
    "iter_trust_log",
    "load_trust_log",
    "get_trust_log_entry",
    "get_trust_log_page",
    "get_trust_logs_by_request",
    "verify_trust_log",
    "write_shadow_decide",
    "get_last_hash",
    "calc_sha256",
    "trust_log_lock",
    "LOG_JSON",
    "LOG_JSONL",
]


# fuji.py 等が append_trust_event として参照するための後方互換エイリアス
append_trust_event = append_trust_log
