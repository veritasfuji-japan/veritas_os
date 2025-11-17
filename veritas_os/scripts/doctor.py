#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""VERITAS Doctor (stable)
veritas_os/scripts/logs 配下のログを解析して、
同じフォルダに doctor_report.json を出力する。
"""

import os
import json
import glob
import statistics
from pathlib import Path
from datetime import datetime

# ==== パス定義 ====
# doctor.py の場所: veritas_os/scripts/doctor.py を想定
HERE = Path(__file__).resolve().parent          # .../veritas_os/scripts
REPO_ROOT = HERE.parent                         # .../veritas_os

# ログ置き場（decide_*.json, health_*.json など）
LOG_DIR = HERE / "logs"                         # .../veritas_os/scripts/logs
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 監査用 JSONL（任意で使う場合）
TRUST_LOG_JSON = LOG_DIR / "trust_log.jsonl"
# 互換のための別名（昔の変数名）
LOG_JSONL = TRUST_LOG_JSON

# ダッシュボード用レポート出力先
REPORT_PATH = LOG_DIR / "doctor_report.json"

# 解析対象パターン（JSONL優先／重複除去）
PATTERNS = [
    "decide_*.jsonl", "health_*.jsonl", "*status*.jsonl", "*.jsonl",
    "decide_*.json",  "health_*.json",  "*status*.json",
]

# キーワード辞書（必要に応じて増やしてOK）
KW_LIST = ["交渉", "天気", "疲れ", "音楽", "VERITAS"]


# ---- helpers -----------------------------------------------------------
def _iter_files() -> list[str]:
    """PATTERNS に一致するログの絶対パスを mtime 昇順で返す（重複除去）"""
    seen, files = set(), []
    for pat in PATTERNS:
        for p in glob.glob(os.path.join(LOG_DIR, pat)):
            if p not in seen and os.path.getsize(p) > 0:
                seen.add(p)
                files.append(p)
    files.sort(key=lambda p: os.path.getmtime(p))
    return files


def _read_json_or_jsonl(path: str) -> list[dict]:
    """
    1ファイルから辞書のリストを返す。
    - 先頭文字で JSON / JSONL を判定
    - 壊れ行はスキップ
    - {"items":[...]} 形式は items を展開
    """
    items: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        head = f.read(1)
        if not head:
            return []
        f.seek(0)

        if head == "{":  # JSON
            data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items.extend(data["items"])
            else:
                items.append(data)
        else:            # JSONL
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    # 破損行は無視して続行
                    continue
    return items


def _bump_kw(counter: dict, text: str):
    for w in KW_LIST:
        if w and (w in (text or "")):
            counter[w] = counter.get(w, 0) + 1


# ---- main analyzer -----------------------------------------------------
def analyze_logs():
    files = _iter_files()

    # TRUST_LOG_JSON がなくても、とりあえず警告だけでOK
    if not files and not os.path.exists(LOG_JSONL):
        print("⚠️ .veritas 内に解析対象のログが見つかりません。")
        return

    found_total  = len(files)
    parsed       = 0
    skipped_zero = 0
    skipped_bad  = 0

    # カテゴリ別メトリクス
    metrics = {
        "decide": {"count": 0},
        "health": {"count": 0},
        "status": {"count": 0},
        "other":  {"count": 0},
    }
    uncertainties: list[float] = []
    keywords: dict[str, int] = {}

    # ファイル群を走査
    for path in files:
        name = os.path.basename(path)
        if   name.startswith("decide_"):  cat = "decide"
        elif name.startswith("health_"):  cat = "health"
        elif "status" in name:            cat = "status"
        else:                             cat = "other"

        try:
            items = _read_json_or_jsonl(path)
        except Exception as e:
            skipped_bad += 1
            print(f"⚠️ {path} の解析中にエラー: {e}")
            continue

        if not items:
            skipped_zero += 1
            continue

        # スキーマ揺れを吸収して抽出
        for data in items:
            if not isinstance(data, dict):
                continue

            # query
            ctx   = data.get("context") or {}
            query = data.get("query") or ctx.get("query") or ""
            if query:
                _bump_kw(keywords, query)

            # 不確実性（あれば）
            chosen = (
                (data.get("response") or {}).get("chosen")
                or (data.get("result") or {}).get("chosen")
                or (data.get("decision") or {}).get("chosen")
                or data.get("chosen")
                or {}
            )
            unc = chosen.get("uncertainty", data.get("uncertainty", None))
            try:
                if unc is not None:
                    uncertainties.append(float(unc))
            except Exception:
                pass

        metrics[cat]["count"] += 1
        parsed += 1

    # 監査 JSONL（任意）を読むだけ読んで最終時刻の補助に使う
    last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if os.path.exists(LOG_JSONL) and os.path.getsize(LOG_JSONL) > 0:
            with open(LOG_JSONL, "r", encoding="utf-8") as f:
                tail = f.readlines()[-20:]
            for line in reversed(tail):
                try:
                    obj = json.loads(line.strip())
                    ts  = (obj.get("created_at") or "").replace("Z", "")
                    if ts:
                        last_check = ts
                        break
                except Exception:
                    continue
    except Exception:
        pass

    avg_unc = round(statistics.mean(uncertainties), 3) if uncertainties else 0.0

    result = {
        "total_files_found": found_total,
        "parsed_logs":       parsed,
        "skipped_zero":      skipped_zero,
        "skipped_badjson":   skipped_bad,
        "avg_uncertainty":   avg_unc,
        "keywords":          keywords,
        "last_check":        last_check,
        "by_category":       {k: v["count"] for k, v in metrics.items()},
        "generated_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_dir":        str(LOG_DIR),
    }

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- console summary ------------------------------------------------
    print("\n== VERITAS Doctor Report ==")
    print("✓ 検出(総):", found_total)
    print("✓ 解析OK :", parsed)
    print("↪ スキップ: 0B=", skipped_zero, ", JSON=", skipped_bad)
    print("🎯 平均不確実性:", avg_unc)
    print("🔑 キーワード出現頻度:", keywords)
    print("📅 最終診断時刻:", last_check)
    print("📊 カテゴリ内訳:", {k: v["count"] for k, v in metrics.items()})
    print("✅ 保存完了:", REPORT_PATH)


if __name__ == "__main__":
    analyze_logs()
