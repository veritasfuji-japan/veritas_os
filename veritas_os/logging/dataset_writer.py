# -*- coding: utf-8 -*-
"""
VERITAS Dataset Writer（拡張版）

機能:
- /v1/decide の決定記録を JSONL に書き出す
- 簡易な統計取得
- 簡易検索
- バリデーション

※ TrustLog とは別に、「学習・評価用データセット」の素になるログ。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from veritas_os.core.config import cfg
from veritas_os.core.decision_status import (
    DecisionStatus,
    normalize_status,
)
from veritas_os.core.atomic_io import atomic_append_line

logger = logging.getLogger(__name__)

# ==========================
# パス設定
# ==========================

# config 側で一元管理された dataset_dir を採用
DATASET_DIR: Path = cfg.dataset_dir
DATASET_DIR.mkdir(parents=True, exist_ok=True)

DATASET_JSONL: Path = DATASET_DIR / "dataset.jsonl"

# ★ C-1 修正: スレッドセーフ化のためのロック
# FastAPI の並行リクエストでデータ破損を防止
_dataset_lock = threading.RLock()


# ==========================
# ヘルパー関数
# ==========================

def _sha256_dict(d: Dict[str, Any]) -> str:
    """辞書を安定化JSONにして SHA-256 ハッシュ化"""
    try:
        s = json.dumps(d, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(d)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _f2(x: Any, default: float = 0.0) -> float:
    """安全な float 変換（失敗時は default）"""
    try:
        return float(x)
    except Exception:
        return default


def _summarize_alternatives(alts: List[Dict[str, Any]] | None, k: int = 5) -> List[Dict[str, Any]]:
    """選択肢を要約（最大 k 件）"""
    out: List[Dict[str, Any]] = []
    for a in (alts or [])[:k]:
        out.append(
            {
                "id": a.get("id"),
                "title": a.get("title") or a.get("text"),
                "score": _f2(a.get("score"), 1.0),
            }
        )
    return out


def _summarize_evidence(evs: List[Dict[str, Any]] | None, k: int = 5) -> List[Dict[str, Any]]:
    """証拠を要約（最大 k 件）"""
    out: List[Dict[str, Any]] = []
    for e in (evs or [])[:k]:
        out.append(
            {
                "source": e.get("source"),
                "confidence": _f2(e.get("confidence"), 0.0),
                "snippet": e.get("snippet"),
            }
        )
    return out


# ==========================
# レコード構築
# ==========================

def build_dataset_record(
    req_payload: Dict[str, Any],
    res_payload: Dict[str, Any],
    meta: Dict[str, Any],
    eval_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    データセットレコードを構築

    Args:
        req_payload: /v1/decide のリクエストJSON
        res_payload: /v1/decide のレスポンスJSON
        meta: API / Kernel バージョンなどのメタ情報
        eval_meta: 人手評価などのメタ情報（任意）

    Returns:
        1行分の JSONL レコード
    """
    chosen = (res_payload or {}).get("chosen") or {}
    alts = (res_payload or {}).get("alternatives") or []
    evs = (res_payload or {}).get("evidence") or []
    fuji = (res_payload or {}).get("fuji") or {}
    gate = (res_payload or {}).get("gate") or {}

    # world は chosen 内にぶら下がっている前提（あれば拾う）
    world = chosen.get("world", {}) if chosen else {}

    # MemoryOS 使用状況
    mem = (res_payload or {}).get("memory", {}) or {}
    mem_used = bool(mem.get("used", False))
    mem_citation = int(mem.get("citations", 0) or 0)

    # FUJI / Gate のステータス（Enumに正規化）
    raw_status = gate.get("decision_status", DecisionStatus.ALLOW.value)
    try:
        status_enum = normalize_status(raw_status)
    except ValueError:
        status_enum = DecisionStatus.ALLOW

    # ラベル（学習用の meta label）
    decision_labels = {
        "status": status_enum.value,          # "allow" / "modify" / "rejected"
        "fuji_status": fuji.get("status"),    # FUJI の内部ステータス（任意）
        "blocked": status_enum is DecisionStatus.REJECTED,
        "memory_used": mem_used,
        "memory_citations": mem_citation,
    }

    rec = {
        "ts": int(time.time() * 1000),
        "request": {
            "payload": req_payload,
            "hash": _sha256_dict(req_payload),
        },
        "response": {
            "payload": res_payload,
            "hash": _sha256_dict(res_payload),
            "chosen": {
                "id": chosen.get("id"),
                "title": chosen.get("title"),
                "score": _f2(chosen.get("score"), 1.0),
                "utility": _f2(world.get("utility"), 0.0),
                "risk": _f2(world.get("predicted_risk"), 0.0),
                "benefit": _f2(world.get("predicted_benefit"), 0.0),
                "cost": _f2(world.get("predicted_cost"), 0.0),
            },
            "alternatives": _summarize_alternatives(alts),
            "evidence": _summarize_evidence(evs),
            "fuji": {
                "status": fuji.get("status"),
                "reasons": fuji.get("reasons", []),
                "violations": fuji.get("violations", []),
            },
            "gate": {
                "decision_status": status_enum.value,
                "risk": _f2(gate.get("risk"), 0.0),
                "telos_score": _f2(gate.get("telos_score"), 0.0),
                "reason": gate.get("reason"),
            },
            "memory": {
                "used": mem_used,
                "citations": mem_citation,
            },
        },
        "meta": meta or {},
        "eval": eval_meta or {},
        "labels": decision_labels,
        "version": {
            "api": (meta or {}).get("api_version"),
            "kernel": (meta or {}).get("kernel_version"),
        },
    }

    return rec


# ==========================
# バリデーション & 追記
# ==========================

def validate_record(record: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    レコードのバリデーション

    Returns:
        (valid, error_message)
    """
    required_fields = ["ts", "request", "response", "labels"]
    for field in required_fields:
        if field not in record:
            return False, f"Missing required field: {field}"

    # ts
    if not isinstance(record["ts"], int) or record["ts"] <= 0:
        return False, "Invalid timestamp"

    # ラベル
    labels = record["labels"]
    if "status" not in labels:
        return False, "Missing status in labels"

    return True, None


def append_dataset_record(
    record: Dict[str, Any],
    path: Path = DATASET_JSONL,
    validate: bool = True,
) -> None:
    """
    データセットに JSONL 形式で1行追記

    ★ C-1 修正: スレッドセーフ化
    - RLock による同時書き込み保護
    - atomic_append_line による fsync 保証
    """
    if validate:
        valid, error = validate_record(record)
        if not valid:
            logger.error("Invalid record: %s", error)
            return

    try:
        # ★ スレッドセーフ: ロックを取得して排他制御
        with _dataset_lock:
            atomic_append_line(path, json.dumps(record, ensure_ascii=False))
    except Exception as e:
        logger.warning("append_dataset_record failed: %s", e)


# ==========================
# 統計 & 検索
# ==========================

def get_dataset_stats(path: Path = DATASET_JSONL) -> Dict[str, Any]:
    """
    データセット統計を取得

    Returns:
        {
            "total_records": int,
            "status_counts": {"allow": N, "modify": M, "rejected": K},
            "memory_usage": {"used": N, "unused": M},
            "avg_score": float,
            "date_range": {"start": "...", "end": "..."}  # ISO8601 (UTC)
        }
    """
    if not path.exists():
        return {
            "total_records": 0,
            "status_counts": {},
            "memory_usage": {},
            "avg_score": 0.0,
            "date_range": None,
        }

    records: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        return {
            "total_records": 0,
            "status_counts": {},
            "memory_usage": {},
            "avg_score": 0.0,
            "date_range": None,
        }

    status_counts: Dict[str, int] = {}
    memory_used_count = 0
    scores: List[float] = []
    timestamps: List[int] = []

    for rec in records:
        # status
        status = rec.get("labels", {}).get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        # memory
        if rec.get("labels", {}).get("memory_used", False):
            memory_used_count += 1

        # score
        raw_score = (
            rec.get("response", {})
            .get("chosen", {})
            .get("score")
        )
        scores.append(_f2(raw_score, 0.0))

        # timestamp
        ts = rec.get("ts")
        if isinstance(ts, int) and ts > 0:
            timestamps.append(ts)

    date_range = None
    if timestamps:
        start_ts = min(timestamps) / 1000.0
        end_ts = max(timestamps) / 1000.0
        date_range = {
            "start": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
        }

    return {
        "total_records": len(records),
        "status_counts": status_counts,
        "memory_usage": {
            "used": memory_used_count,
            "unused": len(records) - memory_used_count,
        },
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
        "date_range": date_range,
    }


def search_dataset(
    query: Optional[str] = None,
    status: Optional[str] = None,
    memory_used: Optional[bool] = None,
    limit: int = 100,
    path: Path = DATASET_JSONL,
) -> List[Dict[str, Any]]:
    """
    データセット検索（軽量版）

    Args:
        query: request.payload.query を対象にした部分一致検索
        status: labels.status でフィルタ（"allow" / "modify" / "rejected" など）
        memory_used: True/False で MemoryOS 使用有無をフィルタ
        limit: 最大件数
        path: JSONL ファイルパス
    """
    if not path.exists():
        return []

    results: List[Dict[str, Any]] = []
    q_lower = query.lower() if query else None

    with path.open(encoding="utf-8") as f:
        for line in f:
            if len(results) >= limit:
                break

            line = line.strip()
            if not line:
                continue

            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # クエリフィルタ
            if q_lower:
                req_query = (
                    rec.get("request", {})
                    .get("payload", {})
                    .get("query", "")
                )
                if q_lower not in str(req_query).lower():
                    continue

            # status フィルタ
            if status:
                rec_status = rec.get("labels", {}).get("status")
                if rec_status != status:
                    continue

            # memory_used フィルタ
            if memory_used is not None:
                rec_memory = rec.get("labels", {}).get("memory_used", False)
                if bool(rec_memory) != memory_used:
                    continue

            results.append(rec)

    return results


__all__ = [
    "build_dataset_record",
    "append_dataset_record",
    "validate_record",
    "get_dataset_stats",
    "search_dataset",
]

