#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS CLI: decide + plan viewer

使い方:
    python3 decide_plan.py "今日やるべきことを整理して"
"""

import os
import sys
import json
import textwrap
import requests

API_URL = os.getenv("VERITAS_API_URL", "http://localhost:8000/v1/decide")
API_KEY = os.getenv("VERITAS_API_KEY", "test-key")  # 自分のキーに合わせて
BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = float(os.getenv("VERITAS_HTTP_TIMEOUT", "10"))

def wrap(text: str, width: int = 70) -> str:
    return "\n        ".join(textwrap.wrap(text, width)) if text else ""


def agi_next_step() -> None:
    """VERITAS AGI の次ステップ提案を表示する。"""
    body = {
        "query": "VERITASをAGI化するために、次に手を入れるべきコード変更を1つだけ提案して。",
        "context": {"user_id": "veritas_dev"},
    }
    response = requests.post(
        f"{BASE_URL}/v1/decide",
        headers={
            "X-API-Key": API_KEY,
            "accept": "application/json",
            "Content-Type": "application/json",
        },
        data=json.dumps(body, ensure_ascii=False),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    # VERITAS_AGI 用のヒントとプランを表示
    extras = data.get("extras", {})
    agi_info = extras.get("veritas_agi") or {}
    print("=== VERITAS AGI snapshot ===")
    print(json.dumps(agi_info.get("snapshot", {}), ensure_ascii=False, indent=2))
    print("meta:", agi_info.get("meta"))
    print("hint:", agi_info.get("hint"))

    print("\n=== 次にやるべきステップ案(Planner) ===")
    planner = extras.get("planner") or {}
    for i, step in enumerate(planner.get("steps", []), 1):
        print(f"{i}. {step.get('title') or step.get('name')}")


def main() -> None:
    """通常の decide + planner 表示を実行する。"""
    if len(sys.argv) >= 2 and sys.argv[1] == "--agi-next-step":
        agi_next_step()
        return

    if len(sys.argv) < 2:
        print("使い方: python3 decide_plan.py \"質問文…\"")
        print("または : python3 decide_plan.py --agi-next-step")
        sys.exit(1)

    query = " ".join(sys.argv[1:]).strip()

    payload = {
        "query": query,
        "context": {
            "user_id": "cli_user",
            "source": "cli",
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    try:
        resp = requests.post(
            API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        print("[ERROR] API 呼び出しに失敗しました:", e)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"[ERROR] status={resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()

    # ---- chosen ----
    chosen = data.get("chosen") or {}
    chosen_title = chosen.get("title") or "(タイトルなし)"
    chosen_desc = chosen.get("description") or ""

    print("====================================")
    print("🧠 VERITAS DECIDE + PLAN (CLI)")
    print("====================================")
    print(f"[Query ] {query}")
    print("")
    print("✅ Chosen")
    print(f"  タイトル: {chosen_title}")
    if chosen_desc:
        print(f"  詳細    : {wrap(chosen_desc)}")
    print("")

    # ---- Planner の取り出し ----
    extras = data.get("extras") or {}
    planner = extras.get("planner") or {}

    steps = planner.get("steps") or []

    if not steps:
        print("📋 Planner: ステップは生成されていません。")
        sys.exit(0)

    print("📋 Planner Steps")
    print("")

    for i, st in enumerate(steps, 1):
        title = st.get("title") or st.get("name") or f"Step {i}"
        detail = st.get("detail") or st.get("description") or ""
        kind = st.get("kind") or st.get("type") or ""

        line = f"{i}. {title}"
        if kind:
            line += f"  [{kind}]"
        print(line)

        if detail:
            print(f"    {wrap(detail, width=72)}")

        # サブタスクがある場合（あれば）
        subs = st.get("substeps") or st.get("tasks") or []
        for j, sub in enumerate(subs, 1):
            s_title = sub.get("title") or sub.get("name") or f"Sub {j}"
            s_detail = sub.get("detail") or sub.get("description") or ""
            print(f"      - {s_title}")
            if s_detail:
                print(f"          {wrap(s_detail, width=68)}")

        print("")

    # メトリクスちょい見せ（任意）
    metrics = (extras.get("metrics") or {})
    if metrics:
        print("---- Metrics ----")
        if "latency_ms" in metrics:
            print(f"  latency_ms         : {metrics['latency_ms']}")
        if "mem_evidence_count" in metrics:
            print(f"  mem_evidence_count : {metrics['mem_evidence_count']}")
        if "avg_world_utility" in metrics:
            print(f"  avg_world_utility  : {metrics['avg_world_utility']}")
        print("")


if __name__ == "__main__":
    main()
