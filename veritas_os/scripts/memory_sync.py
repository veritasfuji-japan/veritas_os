#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ===========================
# VERITAS MemoryOS Sync
# ===========================
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------
# 📂 パス設定（canonical runtime paths）
#   All outputs go to runtime/<namespace>/ (not scripts/logs or .veritas/)
# --------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

# Canonical paths
from veritas_os.scripts._runtime_paths import (  # noqa: E402
    LOG_DIR,
    DOCTOR_REPORT_JSON,
    DATA_DIR,
    ensure_dirs as _ensure_runtime_dirs,
)
REPORT_PATH = DOCTOR_REPORT_JSON

# MemoryOS uses canonical data directory (not .veritas/)
MEM_PATH = DATA_DIR / "memory.json"

USER_ID = os.getenv("VERITAS_USER_ID", "cli")  # 任意で切替

# --------------------------------------------------
# 基本ユーティリティ
# --------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _load_json(path: Path, default):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --- 旧形式 → MemoryOS 標準形式(list) へのマイグレーション -----------------
def _migrate_memory(mem_raw):
    """
    MemoryOS の標準形式に揃える:
      標準: list[ { "user_id", "key", "value", "ts" }, ... ]
    """
    # すでに標準(list)ならそのまま
    if isinstance(mem_raw, list):
        return mem_raw

    migrated = []

    # 旧: {"users":{ user_id:{"history":[{timestamp,report}...] }}, "updated_at":...}
    if isinstance(mem_raw, dict) and "users" in mem_raw:
        users = mem_raw.get("users", {})
        if isinstance(users, dict):
            for uid, uobj in users.items():
                history = []
                if isinstance(uobj, dict):
                    history = uobj.get("history") or []
                if not isinstance(history, list):
                    continue
                for idx, rec in enumerate(history):
                    if not isinstance(rec, dict):
                        continue
                    migrated.append({
                        "user_id": uid or USER_ID,
                        "key": f"report_migrated_{idx}",
                        "value": rec.get("report", rec),
                        "ts": time.time(),
                    })
        return migrated

    # 旧: {"history":[...]} 単独
    if isinstance(mem_raw, dict) and "history" in mem_raw:
        history = mem_raw.get("history") or []
        if isinstance(history, list):
            for idx, rec in enumerate(history):
                if not isinstance(rec, dict):
                    continue
                migrated.append({
                    "user_id": USER_ID,
                    "key": f"report_migrated_{idx}",
                    "value": rec.get("report", rec),
                    "ts": time.time(),
                })
        return migrated

    # dict/その他 → 1 レコードとして包む
    if isinstance(mem_raw, dict):
        migrated.append({
            "user_id": USER_ID,
            "key": "legacy_memory",
            "value": mem_raw,
            "ts": time.time(),
        })
        return migrated

    # 何もなければ空リスト
    return []

# --------------------------------------------------
# メイン: Doctor レポート → MemoryOS へ同期
# --------------------------------------------------

def update_memory(report: dict):
    """VERITAS Doctorの診断結果を MemoryOS の標準形式で蓄積"""

    # 既存メモリ読み込み（壊れていても復旧）
    raw = _load_json(MEM_PATH, [])
    mem_list = _migrate_memory(raw)

    # doctor_report 用のレコードを追加
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    record = {
        "user_id": USER_ID,
        "key": f"doctor_report_{stamp}",
        "value": {
            "kind": "doctor_report",
            "generated_at": report.get("generated_at"),
            "summary": {
                "total_decisions": report.get("total_decisions"),
                "status_counts": report.get("status_counts"),
                "value_ema": report.get("value_ema"),
                "memory": report.get("memory"),
            },
            "raw": report,  # 必要なら丸ごと
        },
        "ts": time.time(),
    }
    mem_list.append(record)

    # 最大 500 件くらいにローテーション
    if len(mem_list) > 500:
        mem_list = mem_list[-500:]

    _save_json(MEM_PATH, mem_list)

    print("🧠 MemoryOS updated")
    print(f"  user:   {USER_ID}")
    print(f"  file:   {MEM_PATH}")
    print(f"  total:  {len(mem_list)}")

# --------------------------------------------------
# CLI 実行時: doctor_report.json を読み込んで同期
# --------------------------------------------------

if __name__ == "__main__":
    if not REPORT_PATH.exists():
        print(f"⚠️ doctor_report.json が見つかりません: {REPORT_PATH}")
        print("   先に generate_report.py または veritas full を実行してレポートを作成してください。")
    else:
        report = _load_json(REPORT_PATH, {})
        if not report:
            print("⚠️ レポートが空/壊れています。同期をスキップします。")
        else:
            update_memory(report)
