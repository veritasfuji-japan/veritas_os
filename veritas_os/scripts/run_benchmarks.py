#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
benchmarks/*.yaml を一括で /v1/decide に投げて、
結果を scripts/logs/benchmarks/ 以下に保存するスクリプト。
"""

import os
import json
import time
import glob
from pathlib import Path

import requests
import yaml

# ==== 設定 ====
BASE_URL = "http://127.0.0.1:8000"
API_KEY = os.getenv("VERITAS_API_KEY", "YOUR_API_KEY_HERE")  # 必要に応じて書き換え

REPO_ROOT = Path(__file__).resolve().parents[1]          # .../veritas_os
BENCH_DIR = REPO_ROOT / "benchmarks"
LOG_ROOT  = REPO_ROOT / "scripts" / "logs" / "benchmarks"
LOG_ROOT.mkdir(parents=True, exist_ok=True)


def run_one_bench(path: Path):
    """単一 YAML ベンチを実行して結果を保存"""
    with open(path, "r", encoding="utf-8") as f:
        bench = yaml.safe_load(f)

    bench_id = bench.get("id") or path.stem
    name     = bench.get("name", "")
    req_body = bench.get("request")

    if not isinstance(req_body, dict):
        print(f"[SKIP] {path} request フォーマット不正")
        return False

    url = f"{BASE_URL}/v1/decide"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    print(f"\n=== RUN BENCH: {bench_id} ({name}) ===")
    t0 = time.time()
    resp = requests.post(url, headers=headers, data=json.dumps(req_body))
    dt = time.time() - t0

    print(f"status={resp.status_code} time={dt:.2f}s")

    out = {
        "bench_id": bench_id,
        "name": name,
        "yaml_path": str(path),
        "request": req_body,
        "status_code": resp.status_code,
        "elapsed_sec": dt,
        "response_json": None,
    }

    try:
        out["response_json"] = resp.json()
    except Exception:
        out["response_json"] = {"raw_text": resp.text}

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = LOG_ROOT / f"{bench_id}_{ts}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"→ saved: {out_path}")
    return resp.ok


def main():
    files = sorted(glob.glob(str(BENCH_DIR / "*.yaml")))
    if not files:
        print(f"[WARN] ベンチマークファイルがありません: {BENCH_DIR}")
        return

    print(f"ベンチマーク {len(files)} 件を実行します")
    ok_cnt = 0

    for fp in files:
        p = Path(fp)
        if run_one_bench(p):
            ok_cnt += 1

    print(f"\n=== DONE ===")
    print(f"成功: {ok_cnt} / {len(files)}")


if __name__ == "__main__":
    main()
