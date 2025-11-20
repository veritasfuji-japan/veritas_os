#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple benchmark runner for VERITAS OS.

- Load benchmarks/agi_mvp_plan.yaml
- Call POST /v1/decide on the local VERITAS API
- Save result to scripts/logs/bench_agi_mvp_plan.json
- Print a short summary (chosen.action / telos_score / fuji.status)
"""

import os
import json
import datetime
from pathlib import Path

import requests
import yaml


# ----- Config -----

API_BASE = os.getenv("VERITAS_API_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("VERITAS_API_KEY", "dev-key")  # ※サーバ側と合わせておく

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os
BENCH_DIR = REPO_ROOT / "benchmarks"

LOG_DIR = REPO_ROOT / "scripts" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def run_bench(yaml_name: str) -> None:
    bench_file = BENCH_DIR / yaml_name
    if not bench_file.exists():
        raise FileNotFoundError(f"benchmark file not found: {bench_file}")

    with open(bench_file, "r", encoding="utf-8") as f:
        bench = yaml.safe_load(f)

    bench_id = bench.get("id", "unknown")
    name = bench.get("name", "")
    req_payload = bench.get("request") or {}

    url = f"{API_BASE}/v1/decide"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    print("=== VERITAS benchmark ===")
    print(f"- id   : {bench_id}")
    print(f"- name : {name}")
    print(f"- POST : {url}")
    print(f"- using API_KEY from env VERITAS_API_KEY")

    resp = requests.post(url, headers=headers, json=req_payload, timeout=120)
    print(f"- HTTP : {resp.status_code}")
    resp.raise_for_status()

    body = resp.json()

    chosen = body.get("chosen") or {}
    fuji = body.get("fuji") or {}

    print("\n--- Decision summary ---")
    print("chosen.action :", chosen.get("action"))
    print("chosen.rationale (short):", (chosen.get("rationale") or "")[:120], "...")
    print("telos_score   :", body.get("telos_score"))
    print("fuji.status   :", fuji.get("status"))
    print("fuji.reasons  :", (fuji.get("reasons") or [])[:3])

    # save full log
    out = {
        "bench_id": bench_id,
        "name": name,
        "run_at": datetime.datetime.now().isoformat(),
        "request": req_payload,
        "response": body,
    }
    out_path = LOG_DIR / f"bench_{bench_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\nSaved bench result -> {out_path}")


if __name__ == "__main__":
    # とりあえず 1 ケースだけ
    run_bench("agi_mvp_plan.yaml")
