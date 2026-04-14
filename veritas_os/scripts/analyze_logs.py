#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Log Analyzer (Doctor Dashboard + CSV + Graph)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# ========================================
#  パス設定（canonical runtime paths）
# ========================================

BASE_DIR = Path(__file__).resolve().parents[1]          # .../veritas_os

# Canonical runtime paths — all outputs go to runtime/<namespace>/
from veritas_os.scripts._runtime_paths import (  # noqa: E402
    LOG_DIR,
    DOCTOR_REPORT_JSON,
)
REPORT_JSON = DOCTOR_REPORT_JSON

# decide_YYYYMMDD_HHMMSS.json または decide_YYYYMMDD_HHMMSS_123.json に対応
FNAME_RE = re.compile(r"decide_(\d{8})_(\d{6})(?:_\d+)?\.json")


# ========================================
#  1) ログ名から timestamp を抽出
# ========================================
def parse_ts_from_name(name: str):
    m = FNAME_RE.search(name)
    if not m:
        return None
    ymd, hms = m.groups()
    try:
        return datetime.strptime(ymd + hms, "%Y%m%d%H%M%S")
    except Exception:
        return None


# ========================================
#  2) JSONセーフ取得
# ========================================
def safe_get(d, *path, default=None):
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


# ========================================
#  3) 1レコード抽出
# ========================================
def extract_one(record: dict) -> dict:
    status, reason, text = None, None, None

    # decide() 系
    if "decision" in record:
        status = safe_get(record, "decision", "chosen")
        reason = safe_get(record, "decision", "reason")

    # fuji 系
    elif "fuji" in record:
        status = safe_get(record, "fuji", "status")
        reasons = safe_get(record, "fuji", "reasons")
        if isinstance(reasons, list) and reasons:
            reason = reasons[0]

    # その他の型
    elif "result" in record:
        status = safe_get(record, "result", "status")

    text = (
        safe_get(record, "meta", "echo", "content")
        or safe_get(record, "context", "query")
        or safe_get(record, "request", "content")
        or safe_get(record, "input")
    )

    return {
        "status": (status or "").lower() or None,
        "reason": reason,
        "text": text,
    }


# ========================================
#  4) ログ読み込み
# ========================================
def load_logs() -> list[dict]:
    if not LOG_DIR.exists():
        print(f"[!] ログフォルダがありません: {LOG_DIR}")
        sys.exit(1)

    rows = []
    for p in sorted(LOG_DIR.glob("decide_*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            info = extract_one(data)
            info["file"] = p.name
            info["timestamp"] = parse_ts_from_name(p.name)
            rows.append(info)
        except Exception as e:
            print(f"[warn] 読み込み失敗 {p.name}: {e}")

    return rows


# ========================================
#  5) 集計（コンソール + Web Doctor JSON）
# ========================================
def summarize(rows: list[dict]) -> dict:
    if not rows:
        print("⚠️ ログがまだありません。まず /v1/decide を実行してください。")
        return {"count": 0, "items": []}

    total = len(rows)
    by_status = Counter(r.get("status") or "unknown" for r in rows)
    by_reason = Counter((r.get("reason") or "n/a") for r in rows)

    print("\n=== ① ステータス別集計 ===")
    for status, cnt in by_status.most_common():
        pct = 100.0 * cnt / total
        print(f"- {status:8s}: {cnt:4d} ({pct:5.1f}%)")
    print(f"- total    : {total:4d}")

    print("\n=== ② 理由トップ10 ===")
    for reason, cnt in by_reason.most_common(10):
        print(f"- {reason}: {cnt}")

    print("\n=== ③ 直近5件 ===")
    latest = sorted(
        [r for r in rows if r.get("timestamp")],
        key=lambda x: x["timestamp"],
        reverse=True
    )[:5]

    for r in latest:
        ts = r["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        status = r.get("status") or "unknown"
        reason = r.get("reason") or "-"
        text = (r.get("text") or "").replace("\n", " ")
        if len(text) > 60:
            text = text[:57] + "..."
        print(f"- {ts} | {status:6s} | {reason:20s} | {text}")

    # Web Doctor 用
    latest_for_json = [
        {
            "time": r["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "status": r.get("status") or "unknown",
            "reason": r.get("reason") or "-",
            "text": r.get("text") or "",
        }
        for r in latest
    ]

    return {
        "count": total,
        "by_status": dict(by_status),
        "by_reason_top10": dict(by_reason.most_common(10)),
        "latest": latest_for_json,
    }


# ========================================
#  6) CSV書き出し
# ========================================
def export_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "status", "reason", "text", "file"])

        for r in sorted(rows, key=lambda x: x.get("timestamp") or datetime.min):
            ts = r["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if r.get("timestamp") else ""
            w.writerow([
                ts,
                r.get("status") or "",
                r.get("reason") or "",
                r.get("text") or "",
                r.get("file") or "",
            ])

    print(f"\n📄 CSVを書き出しました: {out_path}")


# ========================================
#  7) グラフ生成
# ========================================
def make_graphs(rows: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    import matplotlib.pyplot as plt

    # === 1) ステータス別件数 ===
    by_status = Counter(r.get("status") or "unknown" for r in rows)
    labels, values = zip(*sorted(by_status.items()))

    plt.figure()
    plt.bar(labels, values)
    plt.title("Decision count by status")
    plt.xlabel("status")
    plt.ylabel("count")
    p1 = out_dir / "status_counts.png"
    plt.savefig(p1, bbox_inches="tight")
    plt.close()
    paths.append(p1)

    # === 2) 日別 allow率 ===
    by_day_total = defaultdict(int)
    by_day_allow = defaultdict(int)

    for r in rows:
        if not r.get("timestamp"):
            continue
        day = r["timestamp"].strftime("%Y-%m-%d")
        by_day_total[day] += 1
        if (r.get("status") or "").lower() == "allow":
            by_day_allow[day] += 1

    if by_day_total:
        days = sorted(by_day_total.keys())
        rates = [(by_day_allow[d] / by_day_total[d]) * 100.0 for d in days]

        plt.figure()
        plt.plot(days, rates, marker="o")
        plt.title("Allow rate by day")
        plt.xlabel("date")
        plt.ylabel("allow %")
        plt.xticks(rotation=30, ha="right")
        p2 = out_dir / "allow_rate_daily.png"
        plt.savefig(p2, bbox_inches="tight")
        plt.close()
        paths.append(p2)

    return paths


# ========================================
#  8) メイン
# ========================================
def build_parser():
    p = argparse.ArgumentParser(description="VERITAS ログ解析ツール")
    p.add_argument("--graph", action="store_true", help="PNGグラフ生成")
    p.add_argument("--csv", action="store_true", help="CSV出力")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    rows = load_logs()
    summary = summarize(rows)

    # doctor_report.json (Web Doctor用)
    with REPORT_JSON.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n🧾 doctor_report.json を生成しました: {REPORT_JSON}")

    if args.csv or not args.graph:
        export_csv(rows, LOG_DIR / "summary.csv")

    if args.graph:
        imgs = make_graphs(rows, LOG_DIR)
        print("\n🖼 生成したグラフ:")
        for p in imgs:
            print(f"- {p}")

    print("\n✅ 解析が完了しました。")


if __name__ == "__main__":
    main()

