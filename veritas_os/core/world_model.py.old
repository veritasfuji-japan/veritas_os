# veritas/core/world_model.py
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# =========================
# ファイルパス設定
# =========================

# ベースのデータディレクトリ（なければ ~/veritas）
DATA_DIR = Path(os.getenv("VERITAS_DATA_DIR", "~/veritas")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# WorldModel ファイルパス
WORLD_PATH = Path(
    os.getenv("VERITAS_WORLD_STATE", str(DATA_DIR / "world_state.json"))
).expanduser()

DEFAULT_USER_ID = "global"

# =========================
# WorldState データ構造（従来インターフェース）
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

    def progress(self) -> float:
        """プラン進捗率 0〜1"""
        if not self.active_plan_steps:
            return 0.0
        return max(0.0, min(1.0, self.active_plan_done / float(self.active_plan_steps)))


# =========================
# WorldModel ファイルのスキーマ
# =========================

DEFAULT_WORLD: Dict[str, Any] = {
    "schema_version": "1.1.0",
    "updated_at": None,
    "projects": [],   # 各ユーザーごとに最低1つ "user_id:default" プロジェクトを持つ想定
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_world() -> Dict[str, Any]:
    if not WORLD_PATH.exists():
        return {**DEFAULT_WORLD}
    try:
        with WORLD_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # 古い形式（user_id -> state dict）の場合に備えて最低限ラップ
            if "projects" not in data:
                # legacy: { "user_id": {...}, "other_user": {...} }
                projects: List[Dict[str, Any]] = []
                for uid, raw in data.items():
                    if not isinstance(raw, dict):
                        continue
                    metrics = {
                        "decisions": int(raw.get("decisions", 0)),
                        "avg_latency_ms": float(raw.get("avg_latency_ms", 0.0)),
                        "avg_risk": float(raw.get("avg_risk", 0.0)),
                        "avg_value": float(raw.get("avg_value", 0.5)),
                        "active_plan_steps": int(raw.get("active_plan_steps", 0)),
                        "active_plan_done": int(raw.get("active_plan_done", 0)),
                    }
                    last = {
                        "query": raw.get("last_query", ""),
                        "chosen_title": raw.get("last_chosen_title", ""),
                        "decision_status": raw.get("last_decision_status", "unknown"),
                    }
                    projects.append({
                        "project_id": f"{uid}:default",
                        "owner_user_id": uid,
                        "title": f"Default Project for {uid}",
                        "objective": "",
                        "status": "active",
                        "created_at": raw.get("last_updated") or _now_iso(),
                        "last_decision_at": raw.get("last_updated"),
                        "metrics": metrics,
                        "last": last,
                        "decisions": [],
                    })
                return {
                    "schema_version": "1.1.0",
                    "updated_at": _now_iso(),
                    "projects": projects,
                }
            return data
    except Exception:
        pass
    return {**DEFAULT_WORLD}


def _save_world(world: Dict[str, Any]) -> None:
    world["updated_at"] = _now_iso()
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with WORLD_PATH.open("w", encoding="utf-8") as f:
        json.dump(world, f, ensure_ascii=False, indent=2)


def _get_or_create_default_project(world: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    projects = world.setdefault("projects", [])
    proj_id = f"{user_id}:default"

    for p in projects:
        if p.get("project_id") == proj_id:
            return p

    proj = {
        "project_id": proj_id,
        "owner_user_id": user_id,
        "title": f"Default Project for {user_id}",
        "objective": "",
        "status": "active",
        "tags": [],
        "created_at": _now_iso(),
        "last_decision_at": None,
        "metrics": {
            "decisions": 0,
            "avg_latency_ms": 0.0,
            "avg_risk": 0.0,
            "avg_value": 0.5,
            "active_plan_steps": 0,
            "active_plan_done": 0,
        },
        "last": {
            "query": "",
            "chosen_title": "",
            "decision_status": "unknown",
        },
        "decisions": [],
    }
    projects.append(proj)
    return proj


def _project_to_worldstate(user_id: str, proj: Dict[str, Any]) -> WorldState:
    m = proj.get("metrics") or {}
    last = proj.get("last") or {}
    return WorldState(
        user_id=user_id,
        decisions=int(m.get("decisions", 0)),
        avg_latency_ms=float(m.get("avg_latency_ms", 0.0)),
        avg_risk=float(m.get("avg_risk", 0.0)),
        avg_value=float(m.get("avg_value", 0.5)),
        active_plan_id=proj.get("active_plan_id"),
        active_plan_title=proj.get("active_plan_title"),
        active_plan_steps=int(m.get("active_plan_steps", 0)),
        active_plan_done=int(m.get("active_plan_done", 0)),
        last_query=last.get("query", ""),
        last_chosen_title=last.get("chosen_title", ""),
        last_decision_status=last.get("decision_status", "unknown"),
        last_updated=proj.get("last_decision_at") or "",
    )


# =========================
# Public API
# =========================

def load_state(user_id: str = DEFAULT_USER_ID) -> WorldState:
    """
    互換性維持用：
    - world_state.json の "user_id:default" プロジェクトから WorldState を復元
    """
    world = _load_world()
    proj = _get_or_create_default_project(world, user_id)
    return _project_to_worldstate(user_id, proj)


def save_state(state: WorldState) -> None:
    """
    互換性維持用：
    - WorldState を "user_id:default" プロジェクトの metrics/last に反映して保存
    """
    world = _load_world()
    proj = _get_or_create_default_project(world, state.user_id)
    m = proj.setdefault("metrics", {})
    m["decisions"] = int(state.decisions)
    m["avg_latency_ms"] = float(state.avg_latency_ms)
    m["avg_risk"] = float(state.avg_risk)
    m["avg_value"] = float(state.avg_value)
    m["active_plan_steps"] = int(state.active_plan_steps)
    m["active_plan_done"] = int(state.active_plan_done)

    proj["active_plan_id"] = state.active_plan_id
    proj["active_plan_title"] = state.active_plan_title

    last = proj.setdefault("last", {})
    last["query"] = state.last_query
    last["chosen_title"] = state.last_chosen_title
    last["decision_status"] = state.last_decision_status
    proj["last_decision_at"] = state.last_updated or _now_iso()

    _save_world(world)


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
    decide の結果 1件分から、WorldModel を更新する（新: projectベース）
    かつ WorldState を返す（従来インターフェース維持）。
    """
    world = _load_world()
    proj = _get_or_create_default_project(world, user_id)
    metrics = proj.setdefault("metrics", {})
    last = proj.setdefault("last", {})

    # 決定回数
    decisions = int(metrics.get("decisions", 0)) + 1
    metrics["decisions"] = decisions

    # 移動平均（ema_alpha=0.2）
    alpha = 0.2
    risk = float(gate.get("risk", 0.0))
    val = float(values.get("total", values.get("ema", 0.5)))
    prev_risk = float(metrics.get("avg_risk", 0.0))
    prev_val = float(metrics.get("avg_value", 0.5))
    metrics["avg_risk"] = (1 - alpha) * prev_risk + alpha * risk
    metrics["avg_value"] = (1 - alpha) * prev_val + alpha * val

    if latency_ms is not None:
        prev_lat = float(metrics.get("avg_latency_ms", 0.0))
        metrics["avg_latency_ms"] = (1 - alpha) * prev_lat + alpha * float(latency_ms)

    # プラン情報を反映（あれば）
    if planner:
        steps = planner.get("steps") or []
        proj["active_plan_id"] = planner.get("id") or planner.get("plan_id")
        proj["active_plan_title"] = planner.get("title") or planner.get("name")
        metrics["active_plan_steps"] = int(len(steps) or metrics.get("active_plan_steps", 0))
        done = 0
        for s in steps:
            if isinstance(s, dict) and s.get("done"):
                done += 1
        if done:
            metrics["active_plan_done"] = done

    # 最新決定
    last["query"] = query
    last["chosen_title"] = (chosen or {}).get("title") or str(chosen)[:80]
    last["decision_status"] = gate.get("decision_status") or "unknown"
    proj["last_decision_at"] = _now_iso()

    # 決定スナップショットも蓄積しておく（将来のKosmos的解析用）
    req_id = chosen.get("request_id") or values.get("request_id") or ""
    proj.setdefault("decisions", []).append(
        {
            "request_id": req_id,
            "ts": proj["last_decision_at"],
            "query": query,
            "chosen_title": last["chosen_title"],
            "decision_status": last["decision_status"],
            "avg_value_after": metrics["avg_value"],
            "avg_risk_after": metrics["avg_risk"],
        }
    )

    _save_world(world)

    # WorldState に変換して返す
    st = _project_to_worldstate(user_id, proj)
    return st


# ---- decide 前に context に反映 ------------------------
def inject_state_into_context(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    decide 実行前に呼んで、WorldState を context["world_state"] に入れる
    （既存実装と同じキー構造を維持）
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
    シンプルな world.utility 予測。
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
