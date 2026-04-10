# veritas_os/logging/trust_log.py
# 正規TrustLog実装: 論文の式 hₜ = SHA256(hₜ₋₁ || rₜ) に完全準拠
#
# ★ secure-by-default: 保存前に必ず redact → canonicalize → encrypt
#   平文保存はデフォルトで禁止。暗号鍵なしでは書き込みが失敗する。
#
# このモジュールがVERITASの唯一のTrustLog実装です。
# 他のモジュールはここをインポートして使用してください。
#
# 機能:
# - append_trust_log: redact → hash chain → encrypt → append
# - iter_trust_log: decrypt → parse → yield
# - load_trust_log: 最近のエントリをまとめて取得
# - get_trust_log_entry: request_id で単一エントリを取得
# - verify_trust_log: ハッシュチェーンの整合性を検証
# - iso_now: 監査用 UTC ISO8601 時刻
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from veritas_os.logging.paths import LOG_DIR
from veritas_os.logging.rotate import open_trust_log_for_append, load_last_hash_marker
from veritas_os.logging.encryption import (
    encrypt as _encrypt_line,
    decrypt as _decrypt_line,
    is_encryption_enabled,
    EncryptionKeyMissing,
    DecryptionError,
)
from veritas_os.logging.redact import redact_entry as _redact_entry
from veritas_os.core.atomic_io import atomic_write_json, atomic_append_line
from veritas_os.audit.trustlog_signed import (
    SignedTrustLogWriteError,
    append_signed_decision,
)
from veritas_os.security.hash import sha256_hex
from veritas_os.audit.trustlog_verify import verify_full_ledger


def _load_mask_pii():
    """Load `sanitize.mask_pii` with narrow fallback handling.

    Returns:
        Callable mask function when available, otherwise ``None``.

    Raises:
        RuntimeError: Propagated for unexpected import-time failures.
    """
    try:
        from veritas_os.core.sanitize import mask_pii
    except (ImportError, AttributeError) as import_err:  # pragma: no cover
        logging.getLogger(__name__).warning(
            "sanitize.mask_pii unavailable; shadow log PII masking disabled: %s",
            import_err,
        )
        return None
    return mask_pii


_mask_pii = _load_mask_pii()

logger = logging.getLogger(__name__)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)

# trust_log の JSON/JSONL は LOG_DIR 直下に置く
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# trust_log.json に保持する最大件数
MAX_JSON_ITEMS = 2000

# スレッドセーフ化: ハッシュチェーンの整合性を保証するためのロック
# ★ マルチスレッド環境（FastAPI等）での同時書き込みによるチェーン破損を防止
# NOTE: server.py のフォールバック trust log もこのロックを共有する
# IMPORTANT: RLock（リエントラントロック）を使用する理由:
#   log_decision() → get_last_hash() のように、ロック保持中に内部関数が
#   同じロックを再取得するパスが存在する。通常の Lock に変更するとデッドロックする。
#   この依存関係を変更する場合は、全ての呼び出しパスを確認すること。
_trust_log_lock = threading.RLock()
trust_log_lock = _trust_log_lock  # 公開 API（server.py 等から参照用）

# Counters for operational observability
# NOTE: dict を使用することで global 宣言なしに値を更新可能。
# global 宣言忘れによるカウンタ更新漏れ（サイレント失敗）を防止する。
_append_stats: dict[str, int] = {"success": 0, "failure": 0}
_append_stats_lock = threading.Lock()


def get_trust_log_stats() -> dict:
    """Return append success/failure counts for monitoring.

    These counters are process-local and reset on restart.
    Expose via health or metrics endpoints for alerting on persistent failures.
    """
    with _append_stats_lock:
        return {
            "append_success": _append_stats["success"],
            "append_failure": _append_stats["failure"],
        }


# =============================================================================
# ヘルパー関数
# =============================================================================

def iso_now() -> str:
    """ISO8601 UTC時刻（監査ログ標準フォーマット）"""
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: Any) -> str:
    """UTF-8 / bytes から SHA-256 ハッシュを生成"""
    return sha256_hex(data if isinstance(data, bytes) else str(data))


def _canonical_json(obj: Any) -> bytes:
    """RFC 8785 (JCS) 準拠の canonical JSON を UTF-8 バイト列で返す。

    標準の json.dumps との主な差異:
    - 空白なし（separators=(',', ':')）
    - キーは Unicode コードポイント昇順ソート（sort_keys=True）
    - float: Python 依存の repr を避け、整数値は int として出力
    - 文字列: ensure_ascii=False（RFC 8785 は UTF-8 直接出力を推奨）
    - 非シリアライズ値: str() でフォールバックしハッシュ計算を継続

    Note: 完全な RFC 8785 適合には jcs パッケージの導入が推奨されるが、
    追加依存なしで再現性を大幅に向上させる実装として本関数を使用する。
    """
    def _default(v: Any) -> Any:
        return str(v)

    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    ).encode("utf-8")


def _normalize_entry_for_hash(entry: Dict[str, Any]) -> str:
    """
    sha256 計算用にエントリを正規化:
    - sha256 / sha256_prev フィールドは除外
    - RFC 8785 準拠の canonical JSON 化（空白なし・キーソート）
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return _canonical_json(payload).decode("utf-8")


def _compute_sha256(payload: dict) -> str:
    """
    entry 用の SHA-256 ハッシュを計算する。
    - RFC 8785 準拠の canonical JSON でシリアライズ
    - Python バージョン差・float 表現差によるハッシュ変動を抑制
    """
    try:
        s = _canonical_json(payload)
    except (TypeError, ValueError):
        logger.debug("_compute_sha256: canonical JSON failed, using safe fallback", exc_info=True)
        s = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, default=str).encode("utf-8")
    return sha256_hex(s)


def _extract_last_sha256_from_lines(lines: List[str]) -> str | None:
    """Return the newest usable ``sha256`` value from JSONL lines.

    The tail chunk used by :func:`get_last_hash` may include partially written
    trailing data (for example if a previous process crashed mid-write).
    Instead of failing hard on the last line, this helper scans backward and
    returns the most recent decodable JSON object containing a string ``sha256``
    field.

    ★ 暗号化された行は自動復号してからパースする。

    Security:
        Canonical SHA-256 hex values are preferred. If no canonical value is
        present, this function falls back to the newest non-empty string for
        backward compatibility with legacy logs, while emitting a warning.
    """
    fallback_sha: str | None = None

    for line in reversed(lines):
        if not line:
            continue
        try:
            # ★ 暗号化行の復号
            decoded_line = _decrypt_line(line)
            payload = json.loads(decoded_line)
        except (json.JSONDecodeError, ValueError, EncryptionKeyMissing, DecryptionError):
            continue

        sha = payload.get("sha256") if isinstance(payload, dict) else None
        if not isinstance(sha, str) or not sha:
            continue

        if _SHA256_HEX_RE.fullmatch(sha):
            return sha

        if fallback_sha is None:
            fallback_sha = sha

    if fallback_sha is not None:
        logger.warning(
            "Found non-canonical sha256 in trust log tail; using fallback value"
        )
    return fallback_sha


def _recover_last_hash_from_rotated_log() -> str | None:
    """Recover the previous chain hash from a rotated JSONL log.

    Recovery is used only when the active log is empty/missing and the
    rotation marker file is unavailable. This protects hash-chain continuity
    after a marker loss event.
    """
    rotated_log = LOG_JSONL.parent / f"{LOG_JSONL.stem}_old{LOG_JSONL.suffix}"
    if not rotated_log.exists() or rotated_log.stat().st_size == 0:
        return None

    try:
        file_size = rotated_log.stat().st_size
        with open(rotated_log, "rb") as f:
            start = max(0, file_size - 65536)
            while True:
                f.seek(start)
                raw = f.read(file_size - start)
                chunk = raw.decode("utf-8", errors="replace")
                lines = chunk.splitlines()
                if not lines:
                    return None

                if "\n" not in chunk and start > 0:
                    start = max(0, start - 65536)
                    continue

                sha = _extract_last_sha256_from_lines(lines)
                if sha is not None:
                    logger.warning(
                        "Recovered trust log chain hash from rotated file because marker is missing"
                    )
                    return sha
                if start == 0:
                    return None
                start = max(0, start - 65536)
    except OSError:
        logger.warning("Failed to recover last hash from rotated trust log", exc_info=True)
    return None


def _get_last_hash_unlocked() -> str | None:
    """ロックなしで最終ハッシュを取得する内部版。

    呼び出し側が _trust_log_lock を保持していることを前提とする。
    """
    try:
        if not LOG_JSONL.exists():
            marker_hash = load_last_hash_marker(LOG_JSONL)
            if marker_hash:
                return marker_hash
            logger.warning(
                "trust log marker is missing while active log does not exist; attempting rotated-log recovery"
            )
            return _recover_last_hash_from_rotated_log()
        file_size = LOG_JSONL.stat().st_size
        if file_size == 0:
            marker_hash = load_last_hash_marker(LOG_JSONL)
            if marker_hash:
                return marker_hash
            logger.warning(
                "trust log marker is missing while active log is empty; attempting rotated-log recovery"
            )
            return _recover_last_hash_from_rotated_log()
        with open(LOG_JSONL, "rb") as f:
            start = max(0, file_size - 65536)
            while True:
                f.seek(start)
                raw = f.read(file_size - start)
                chunk = raw.decode("utf-8", errors="replace")
                lines = chunk.splitlines()
                if not lines:
                    return None

                if "\n" not in chunk and start > 0:
                    start = max(0, start - 65536)
                    continue

                sha = _extract_last_sha256_from_lines(lines)
                if sha is not None:
                    return sha
                if start == 0:
                    return None
                start = max(0, start - 65536)
    except OSError as exc:
        logger.warning("get_last_hash failed: %s", exc)
    return None


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
        return _get_last_hash_unlocked()


def calc_sha256(payload: dict) -> str:
    """entry の SHA-256 ハッシュを計算する（外部用の薄いヘルパー）

    NOTE: ensure_ascii=False を使用してハッシュチェーンの
    append_trust_log / verify_trust_log と整合性を保つ。

    以前は ``json.dumps`` の失敗時に ``TypeError`` をそのまま送出していたが、
    ``_compute_sha256`` と挙動をそろえるため ``default=str`` フォールバックを
    含む実装に統一する。
    """
    return _compute_sha256(payload)


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
    except (OSError, json.JSONDecodeError):
        logger.warning("_load_logs_json: failed to load %s", LOG_JSON, exc_info=True)
        return []


def _save_json(items: list) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(LOG_JSON, {"items": items}, indent=2)


def append_trust_log(entry: dict) -> Dict[str, Any]:
    """
    決定ごとの監査ログ（軽量）を JSONL + JSON に保存。

    ★ secure-by-default パイプライン:
        1. redact   — PII / secret を自動マスキング
        2. canonicalize — RFC 8785 canonical JSON 化
        3. chain hash — hₜ = SHA256(hₜ₋₁ || rₜ)
        4. encrypt  — 暗号化（鍵未設定時はエラー）
        5. append   — JSONL に追記

    論文の式:
        hₜ = SHA256(hₜ₋₁ || rₜ)

    - JSONL は 5000 行でローテーション（rotate.py 側）
    - trust_log.json は最新 MAX_JSON_ITEMS 件だけ保持

    ★ スレッドセーフ: RLock で全操作を保護（ハッシュチェーンの整合性保証）

    Returns:
        sha256, sha256_prev が付与された *redacted* エントリ

    Raises:
        EncryptionKeyMissing: 暗号鍵が未設定の場合。
        OSError: ファイル I/O に失敗した場合。
        TypeError: エントリが JSON へシリアライズ不能な型を含む場合。
        ValueError: 不正なエントリ値や JSON 変換エラーが発生した場合。
    """
    import os

    # ★ スレッドセーフ: ハッシュチェーンの整合性を保証するためロックを取得
    try:
        with _trust_log_lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            # ---- 直前ハッシュの取得（JSONL 側を正とする）----
            # ★ ロック保持中のためロック不要版を使用（RLock再入を回避）
            sha256_prev = _get_last_hash_unlocked()

            items = _load_logs_json()

            # 元 entry を壊さないようにコピー
            entry = dict(entry)
            entry.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            entry["sha256_prev"] = sha256_prev

            # ★ Step 1: redact — PII / secret を自動マスキング
            entry = _redact_entry(entry)

            # ★ Step 2: canonicalize + Step 3: chain hash
            # rₜ を RFC 8785 canonical JSON化（キーソート・空白なし・一意性保証）
            entry_json = _normalize_entry_for_hash(entry)

            # hₜ₋₁ || rₜ を結合
            if sha256_prev:
                combined = sha256_prev + entry_json
            else:
                combined = entry_json

            # SHA-256計算: hₜ = SHA256(hₜ₋₁ || rₜ)
            entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

            # ★ Step 4: encrypt (mandatory by default)
            line = json.dumps(entry, ensure_ascii=False)
            line = _encrypt_line(line)

            # ★ Step 4.1: encryption enforcement verification (fail-closed)
            if is_encryption_enabled() and not line.startswith("ENC:"):
                raise EncryptionKeyMissing(
                    "Plaintext write blocked by policy: encryption is enabled "
                    "but _encrypt_line() returned non-encrypted output"
                )

            # ★ Step 5: append to JSONL (with fsync for durability)
            with open_trust_log_for_append() as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

            # ---- JSON(配列) を更新（最新 N 件だけ残す）----
            items.append(entry)
            if len(items) > MAX_JSON_ITEMS:
                items = items[-MAX_JSON_ITEMS:]

            _save_json(items)

            # Signed TrustLog (append-only JSONL) is best-effort and must not
            # break the existing decision pipeline.
            try:
                append_signed_decision(entry)
            except SignedTrustLogWriteError:
                logger.warning(
                    "append_signed_decision failed; continuing with legacy trust log",
                    exc_info=True,
                )

            with _append_stats_lock:
                _append_stats["success"] += 1

            return entry

    except (OSError, TypeError, ValueError, json.JSONDecodeError, EncryptionKeyMissing):
        with _append_stats_lock:
            _append_stats["failure"] += 1
        logger.error(
            "append_trust_log failed (failure #%d); hash chain integrity may be affected",
            _append_stats["failure"],
            exc_info=True,
        )
        raise


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

def _decode_line(raw_line: str) -> Optional[Dict[str, Any]]:
    """Decrypt (if needed) and JSON-parse a single JSONL line.

    Returns None for lines that cannot be decoded (blank, corrupt, or
    missing decryption key).
    """
    line = raw_line.strip()
    if not line:
        return None
    try:
        # ★ 暗号化されている行は ENC: プレフィックス付き → 復号
        line = _decrypt_line(line)
        return json.loads(line)
    except (json.JSONDecodeError, ValueError, EncryptionKeyMissing, DecryptionError):
        return None


def iter_trust_log(reverse: bool = False) -> Iterable[Dict[str, Any]]:
    """
    TrustLog を1行ずつイテレートするジェネレータ

    Args:
        reverse: True の場合、末尾から逆順に返す

    Yields:
        dict: 個々のログエントリ（暗号化行は自動復号される）

    ★ スレッドセーフ: ファイル読み込みをロック下で行い、
      書き込み中の不完全な行を読み込むリスクを排除する。
    """
    if not LOG_JSONL.exists():
        return

    try:
        if reverse:
            with _trust_log_lock:
                with LOG_JSONL.open("rb") as f:
                    raw_lines = f.readlines()
            for line in reversed(raw_lines):
                entry = _decode_line(line.decode("utf-8", errors="replace"))
                if entry is not None:
                    yield entry
        else:
            with _trust_log_lock:
                with LOG_JSONL.open("r", encoding="utf-8") as f:
                    raw_lines = f.readlines()
            for line in raw_lines:
                entry = _decode_line(line)
                if entry is not None:
                    yield entry
    except OSError as e:
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


_TRUST_LOG_PAGE_WARN_THRESHOLD = 10_000  # 全件ロード時に警告するエントリ数の閾値


def get_trust_log_page(cursor: Optional[str], limit: int) -> Dict[str, Any]:
    """最新→過去の順で TrustLog をページング取得する。

    Notes:
        API は必ず cursor/limit で返却し、全件返却を回避する。

    Warning:
        現実装は全エントリをメモリに読み込んでからスライスする。
        エントリ数が多い場合はメモリ使用量に注意。
        大規模運用では JSONL をオフセットシークするストリーミング実装への移行を推奨。
    """
    offset, safe_limit = _coerce_pagination(cursor, limit)
    entries = load_trust_log(limit=None)
    if len(entries) > _TRUST_LOG_PAGE_WARN_THRESHOLD:
        logger.warning(
            "get_trust_log_page: loaded %d entries into memory. "
            "Consider streaming implementation for large-scale deployments.",
            len(entries),
        )
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
    """Verify encrypted full TrustLog integrity with stable compatibility fields."""
    try:
        result = verify_full_ledger(log_path=LOG_JSONL, max_entries=max_entries)
    except OSError as exc:
        logger.warning("verify_trust_log failed: %s", exc)
        return {
            "ok": False,
            "checked": 0,
            "broken": True,
            "broken_index": 0,
            "broken_reason": "verification_exception",
            "summary": {
                "total_entries": 0,
                "valid_entries": 0,
                "invalid_entries": 0,
                "chain_ok": False,
                "signature_ok": True,
                "linkage_ok": True,
                "mirror_ok": True,
                "last_hash": None,
                "detailed_errors": [
                    {"ledger": "full", "index": 0, "reason": "verification_exception"}
                ],
            },
        }

    broken_reason = None
    broken_index = None
    if result["detailed_errors"]:
        first = result["detailed_errors"][0]
        broken_reason = first.get("reason")
        broken_index = first.get("index")

    return {
        "ok": result["ok"],
        "checked": result["total_entries"],
        "broken": not result["ok"],
        "broken_index": broken_index,
        "broken_reason": broken_reason,
        "summary": {
            "total_entries": result["total_entries"],
            "valid_entries": result["valid_entries"],
            "invalid_entries": result["invalid_entries"],
            "chain_ok": result["chain_ok"],
            "signature_ok": result["signature_ok"],
            "linkage_ok": result["linkage_ok"],
            "mirror_ok": result["mirror_ok"],
            "last_hash": result["last_hash"],
            "detailed_errors": result["detailed_errors"],
        },
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
    "get_trust_log_stats",
    "trust_log_lock",
    "LOG_JSON",
    "LOG_JSONL",
    "EncryptionKeyMissing",
    "DecryptionError",
]


# fuji.py 等が append_trust_event として参照するための後方互換エイリアス
append_trust_event = append_trust_log
