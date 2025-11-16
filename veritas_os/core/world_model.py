# veritas/core/world_model.py
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 1ファイルにユーザーごとの state をまとめて保存する
STATE_FILE = Path(
    os.getenv("VERITAS_WORLD_STATE", "~/veritas/world_state.json")
).expanduser()

DEFAULT_USER_ID = "global"


# =========================
# WorldState データ構造
# =========================
@dataclass
class WorldState:
    user_id: str = DEFAULT_USER_ID

    # 決定ログから学ぶ統計
    decisions: int = 0
    avg_latency_ms: float = 0.0
    avg_risk: float = 0.0          # FUJI risk の移動平均
    avg_value: float = 0.5         # ValueCore total の移動平均(0〜1)

    # 進行中のプラン
    active_plan_id: Optional[str] = None
    active_plan_title: Optional[str] = None
    active_plan_steps: int = 0
    active_plan_done: int = 0      # 完了したステップ数 (0〜active_plan_steps)

    # 最新コンテキスト
    last_query: str = ""
    last_chosen_title: str = ""
    last_decision_status: str = "unknown"

    # メタ
    last_updated: str = ""

    # ---- util ----
    def progress(self) -> float:
        """プラン進捗率 0〜1"""
        if not self.active_plan_steps:
            return 0.0
        return max(0.0, min(1.0, self.active_plan_done / float(self.active_plan_steps)))


# =========================
# 低レベル I/O
# =========================
def _load_all() -> Dict[str, Dict[str, Any]]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_all(all_states: Dict[str, Dict[str, Any]]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_states, f, ensure_ascii=False, indent=2)


# =========================
# Public API
# =========================
def load_state(user_id: str = DEFAULT_USER_ID) -> WorldState:
    all_states = _load_all()
    raw = all_states.get(user_id) or {}
    if not isinstance(raw, dict):
        raw = {}
    return WorldState(user_id=user_id, **{k: v for k, v in raw.items() if k != 
"user_id"})


def save_state(state: WorldState) -> None:
    all_states = _load_all()
    all_states[state.user_id] = asdict(state)
    all_states[state.user_id]["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_all(all_states)


# ---- state 更新（/v1/decide 後に呼ぶ）-----------------
def update_from_decision(
    *,
    user_id: str,
    query: str,
    chosen: Dict[str, Any],
    gate: Dict[str, Any],
    values: Dict[str, Any],
    planner: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[float] = None,
) -> WorldState:
    """
    decide の結果 1件分から、WorldState を更新する
    """
    st = load_state(user_id)

    st.decisions += 1

    # 移動平均（単純に ema_alpha=0.2 くらい）
    alpha = 0.2

    risk = float(gate.get("risk", 0.0))
    val = float(values.get("total", 0.5))

    st.avg_risk = (1 - alpha) * st.avg_risk + alpha * risk
    st.avg_value = (1 - alpha) * st.avg_value + alpha * val

    if latency_ms is not None:
        st.avg_latency_ms = (1 - alpha) * st.avg_latency_ms + alpha * float(latency_ms)

    # プラン情報を反映（あれば）
    if planner:
        steps = planner.get("steps") or []
        st.active_plan_id = planner.get("id") or planner.get("plan_id")
        st.active_plan_title = planner.get("title") or planner.get("name")
        st.active_plan_steps = int(len(steps) or st.active_plan_steps)
        # done 数は planner 側で "done": true がついていたら数える
        done = 0
        for s in steps:
            if isinstance(s, dict) and s.get("done"):
                done += 1
        if done:
            st.active_plan_done = done

    # 最新決定
    st.last_query = query
    st.last_chosen_title = (chosen or {}).get("title") or str(chosen)[:80]
    st.last_decision_status = gate.get("decision_status") or "unknown"

    st.last_updated = datetime.now(timezone.utc).isoformat()

    save_state(st)
    return st


# ---- decide 前に context に反映 ------------------------
def inject_state_into_context(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    decide 実行前に呼んで、WorldState を context["world_state"] に入れる
    """
    st = load_state(user_id)
    ctx = dict(context or {})
    ctx.setdefault("world_state", {})
    ctx["world_state"].update(
        {
            "decisions": st.decisions,
            "avg_latency_ms": st.avg_latency_ms,
            "avg_risk": st.avg_risk,
            "avg_value": st.avg_value,
            "plan_progress": st.progress(),
            "active_plan_title": st.active_plan_title,
            "last_query": st.last_query,
            "last_chosen_title": st.last_chosen_title,
            "last_decision_status": st.last_decision_status,
            "last_updated": st.last_updated,
        }
    )
    return ctx


# ---- options ごとの world シミュレーション -------------
def simulate(option: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    すごくシンプルな world.utility 予測。
    - base = option["score"]（0〜?）
    - value が高いほど +, risk が高いほど -, plan_progress が高いほど +
    """
    st_dict = (context or {}).get("world_state") or {}
    avg_value = float(st_dict.get("avg_value", 0.5))          # 0〜1
    avg_risk = float(st_dict.get("avg_risk", 0.0))            # 0〜1
    progress = float(st_dict.get("plan_progress", 0.0))       # 0〜1

    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    base = float(option.get("score", 1.0))
    # 0〜1 にざっくり正規化した上で重み付け
    base01 = _clip01(base / 2.0)  # 雑に 0〜2 を 0〜1 へ

    util = base01
    util *= 0.4 + 0.6 * _clip01(avg_value)      # 価値が高いほど↑
    util *= 1.0 - 0.5 * _clip01(avg_risk)       # リスクが高いほど↓
    util *= 0.7 + 0.3 * _clip01(progress)       # 進行中プランと整合するほど↑

    util = _clip01(util)

    # 信頼度は「決定回数が多いほど↑」
    decisions = int(st_dict.get("decisions", 0))
    confidence = 1.0 - math.exp(-decisions / 50.0)  # 0〜1 に漸近

    return {
        "utility": util,
        "confidence": confidence,
        "avg_value": avg_value,
        "avg_risk": avg_risk,
        "plan_progress": progress,
    }
