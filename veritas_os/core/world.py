# veritas_os/core/world.py
"""
VERITAS WorldOS - Unified World State Management

統合版: world_model.pyとworld.pyの機能を統合
- プロジェクトベースの状態管理（from world_model.py）
- 外部知識統合（from world.py）
- Kosmos因果モデル（from world.py）
- AGI Research統合（from world.py）
"""

from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# =========================
# ファイルパス設定
# =========================

# ベースのデータディレクトリ（環境変数優先、なければ ~/veritas）
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
    """
    ユーザー/プロジェクトごとのワールド状態
    従来のインターフェースとの互換性を維持
    """
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


@dataclass
class WorldTransition:
    """
    因果モデル用: 1 decision に対応する「予測 vs 観測」の記録
    """
    ts: str
    user_id: str
    project_id: str
    query: str

    # 予測
    predicted_utility: float
    predicted_risk: float
    predicted_value: float

    # 観測
    observed_gate_status: str
    observed_risk: float
    observed_value: float
    observed_latency_ms: Optional[float] = None

    # 差分（学習用）
    prediction_error: float = 0.0


# =========================
# WorldModel ファイルのスキーマ
# =========================

DEFAULT_WORLD: Dict[str, Any] = {
    "schema_version": "2.0.0",
    "updated_at": None,
    "meta": {
        "version": "2.0",
        "created_at": None,
        "last_users": {},
    },
    "projects": [],   # プロジェクトベース管理
    "veritas": {      # VERITAS全体のトップレベル状態
        "progress": 0.0,
        "decision_count": 0,
        "last_risk": 0.0,
    },
    "metrics": {      # 全体メトリクス
        "value_ema": 0.0,
        "latency_ms_median": 0.0,
        "error_rate": 0.0,
    },
    "external_knowledge": {  # 外部知識統合
        "agi_research_events": [],
        "agi_research": {},
    },
    "history": {      # 因果履歴
        "decisions": [],
        "transitions": [],
    },
}


# =========================
# ユーティリティ関数
# =========================

def _now_iso() -> str:
    """現在時刻をISO 8601形式で返す"""
    return datetime.now(timezone.utc).isoformat()


def _clip01(x: float) -> float:
    """値を0.0〜1.0にクリップ"""
    return max(0.0, min(1.0, float(x)))


def _get_memory_path() -> Path:
    """
    MemoryOS 用の memory.json のパスを推定する

    優先順位:
    1) VERITAS_MEMORY_PATH
    2) VERITAS_LOG_DIR/memory.json
    3) WORLD_STATE_PATH と同じディレクトリの memory.json
    """
    env_mem = os.getenv("VERITAS_MEMORY_PATH")
    if env_mem:
        return Path(env_mem)

    log_dir_env = os.getenv("VERITAS_LOG_DIR")
    if log_dir_env:
        return Path(log_dir_env) / "memory.json"

    return WORLD_PATH.parent / "memory.json"


# =========================
# 外部知識統合（from world.py）
# =========================

def _load_memory_agi_summary(state: dict) -> dict:
    """
    world_state.json 内の external_knowledge から
    AGI 論文リサーチの要約だけを取り出して、LLM 用に軽量サマリ化する

    期待している構造:
    state["external_knowledge"]["agi_research_events"] = [
        {
            "kind": "agi_research",
            "ts": ...,
            "query": "...",
            "papers": [
                {"title": "...", "url": "...", "snippet": "..."},
                ...
            ],
            "summary": "..."
        },
        ...
    ]
    """
    try:
        ext = state.get("external_knowledge") or {}
        events = ext.get("agi_research_events") or []

        if not isinstance(events, list) or not events:
            return {}

        last = events[-1]
        if not isinstance(last, dict):
            return {}

        titles: list[str] = []
        urls: list[str] = []
        for p in last.get("papers") or []:
            if not isinstance(p, dict):
                continue
            t = p.get("title") or ""
            u = p.get("url") or ""
            if t:
                titles.append(t)
            if u:
                urls.append(u)

        return {
            "count": len(events),
            "last_ts": last.get("ts"),
            "last_query": last.get("query"),
            "last_titles": titles[:5],
            "last_urls": urls[:5],
            "last_summary": last.get("summary", ""),
        }

    except Exception as e:
        print("[world] _load_memory_agi_summary error:", e)
        return {}


def _ensure_v2_shape(state: dict) -> dict:
    """
    v1 互換を保ちつつ、v2.0 の最低限のフィールドを保証する
    既存 world_state.json を壊さないように「足りないキーだけ追加」
    """
    # メタ情報
    meta = state.setdefault("meta", {})
    meta.setdefault("version", "2.0")
    meta.setdefault("created_at", _now_iso())
    meta.setdefault("last_users", {})

    # VERITAS 全体のトップレベル状態
    veritas = state.setdefault("veritas", {})
    veritas.setdefault("progress", 0.0)
    veritas.setdefault("decision_count", 0)
    veritas.setdefault("last_risk", 0.0)

    # 全体メトリクス
    metrics = state.setdefault("metrics", {})
    metrics.setdefault("value_ema", 0.0)
    metrics.setdefault("latency_ms_median", 0.0)
    metrics.setdefault("error_rate", 0.0)

    # プロジェクト管理
    if "projects" not in state:
        state["projects"] = []

    # 因果履歴
    history = state.setdefault("history", {})
    history.setdefault("decisions", [])
    history.setdefault("transitions", [])

    # 外部知識
    ext = state.setdefault("external_knowledge", {})
    ext.setdefault("agi_research_events", [])
    ext.setdefault("agi_research", {})

    # スキーマ
    state.setdefault("schema_version", "2.0.0")
    state.setdefault("updated_at", _now_iso())

    return state


# =========================
# ファイル読み書き
# =========================

def _load_world() -> Dict[str, Any]:
    """world_state.json を読み込む（なければデフォルト構造）"""
    try:
        if WORLD_PATH.exists():
            with WORLD_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                data = deepcopy(DEFAULT_WORLD)

            # 古い形式（user_id -> state dict）からの移行処理
            if "projects" not in data and "schema_version" not in data:
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

                data = {
                    "schema_version": "2.0.0",
                    "updated_at": _now_iso(),
                    "projects": projects,
                }

            return _ensure_v2_shape(data)

        # ファイルが存在しない場合はデフォルト
        default_state = deepcopy(DEFAULT_WORLD)
        default_state["meta"]["created_at"] = _now_iso()
        return _ensure_v2_shape(default_state)

    except Exception as e:
        print("[world] load error:", e)
        default_state = deepcopy(DEFAULT_WORLD)
        default_state["meta"]["created_at"] = _now_iso()
        return _ensure_v2_shape(default_state)


def _save_world(world: Dict[str, Any]) -> None:
    """world_state.json に保存"""
    try:
        world = _ensure_v2_shape(world)
        world["updated_at"] = _now_iso()
        world["schema_version"] = "2.0.0"

        WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)

        with WORLD_PATH.open("w", encoding="utf-8") as f:
            json.dump(world, f, ensure_ascii=False, indent=2)

        print(f"[world] state saved -> {WORLD_PATH}")

    except Exception as e:
        print("[world] save error:", e)


# =========================
# プロジェクト管理
# =========================

def _get_or_create_default_project(world: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    デフォルトプロジェクトを取得または作成

    - projects が list / dict / 変な値 どれでも安全に扱う
    - dict の場合は list に正規化して world["projects"] に戻す
    - list 内に str などが混じっていても dict 以外は無視
    """
    proj_id = f"{user_id}:default"
    projects = world.get("projects")

    # --- 1) dict -> list に正規化（古い world_model 由来など） ---
    if isinstance(projects, dict):
        normalized: List[Dict[str, Any]] = []
        for pid, p in projects.items():
            if not isinstance(p, dict):
                continue
            q = dict(p)
            q.setdefault("project_id", pid)
            normalized.append(q)
        projects = normalized
        world["projects"] = projects

    # --- 2) list 以外だったら、素直に作り直す ---
    if not isinstance(projects, list):
        projects = []
        world["projects"] = projects

    # --- 3) 既存 list から該当プロジェクトを探す（dict だけ見る） ---
    for p in projects:
        if not isinstance(p, dict):
            # 文字列など壊れかけ要素は無視
            continue
        if p.get("project_id") == proj_id:
            return p

    # --- 4) 見つからなければ新規作成 ---
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
    world["projects"] = projects
    return proj



def _ensure_project(state: dict, project_id: str, title: str) -> dict:
    """指定されたproject_idのプロジェクトを取得または作成"""
    projects = state.setdefault("projects", [])

    # list形式の場合
    if isinstance(projects, list):
        for p in projects:
            if p.get("project_id") == project_id:
                return p

        # 新規作成
        proj = {
            "project_id": project_id,
            "title": title,
            "status": "active",
            "created_at": _now_iso(),
            "decision_count": 0,
            "progress": 0.0,
            "last_risk": 0.0,
            "notes": "",
        }
        projects.append(proj)
        return proj

    # dict形式の場合（後方互換）
    elif isinstance(projects, dict):
        if project_id not in projects:
            projects[project_id] = {
                "name": title,
                "status": "active",
                "created_at": _now_iso(),
                "decision_count": 0,
                "progress": 0.0,
                "last_risk": 0.0,
                "notes": "",
            }
        return projects[project_id]

    # その他の場合は新規作成
    else:
        state["projects"] = []
        proj = {
            "project_id": project_id,
            "title": title,
            "status": "active",
            "created_at": _now_iso(),
            "decision_count": 0,
            "progress": 0.0,
            "last_risk": 0.0,
            "notes": "",
        }
        state["projects"].append(proj)
        return proj


def _project_to_worldstate(user_id: str, proj: Dict[str, Any]) -> WorldState:
    """プロジェクトデータをWorldStateに変換"""
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
        active_plan_steps=int(m.get("active_plan_steps", m.get("metrics", {}).get("active_plan_steps", 0))),
        active_plan_done=int(m.get("active_plan_done", m.get("metrics", {}).get("active_plan_done", 0))),
        last_query=last.get("query", ""),
        last_chosen_title=last.get("chosen_title", ""),
        last_decision_status=last.get("decision_status", "unknown"),
        last_updated=proj.get("last_decision_at") or "",
    )


# =========================
# Public API - 基本操作
# =========================

def load_state(user_id: str = DEFAULT_USER_ID) -> WorldState:
    """
    ユーザーのワールド状態を読み込む

    Args:
        user_id: ユーザーID（デフォルト: "global"）

    Returns:
        WorldState: ワールド状態
    """
    world = _load_world()
    proj = _get_or_create_default_project(world, user_id)
    return _project_to_worldstate(user_id, proj)


def save_state(state: WorldState) -> None:
    """
    ワールド状態を保存

    Args:
        state: 保存するWorldState
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


def get_state(user_id: str = DEFAULT_USER_ID) -> dict:
    """
    生のワールド状態を取得（後方互換用）

    Args:
        user_id: ユーザーID（現在は未使用・将来拡張用）

    Returns:
        dict: 生のワールド状態
    """
    return _load_world()

def snapshot(project: str) -> Dict[str, Any]:
    """
    後方互換用の WorldModel スナップショット API。

    - 典型的な呼び出し: snapshot("veritas_agi")
    - 返り値は {"progress": float, "decision_count": int, ...} のような dict を想定
    - 内部では get_state() を読み、可能な範囲で progress / decision_count を埋める。
    """

    state = get_state() or {}

    # 1) すでに project キーがトップレベルにある場合はそのまま返す
    proj = state.get(project)
    if isinstance(proj, dict):
        return proj

    # 2) "veritas" ルートに progress / decision_count があるケースを優先
    ver = state.get("veritas")
    if isinstance(ver, dict):
        return {
            "progress": float(ver.get("progress", 0.0) or 0.0),
            "decision_count": int(ver.get("decision_count", 0) or 0),
        }

    # 3) 最後の保険として、state 自体に progress などがあればそれを使う
    if isinstance(state, dict) and (
        "progress" in state or "decision_count" in state
    ):
        return {
            "progress": float(state.get("progress", 0.0) or 0.0),
            "decision_count": int(state.get("decision_count", 0) or 0),
        }

    # 4) 何も取れない場合は空 dict（呼び出し側でデフォルト処理される想定）
    return {}


# =========================
# Public API - 決定後の更新
# =========================

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
    決定結果からワールド状態を更新

    Args:
        user_id: ユーザーID
        query: クエリ
        chosen: 選択された決定
        gate: FUJIゲート結果
        values: Value評価結果
        planner: プランナー結果（オプション）
        latency_ms: レイテンシ（オプション）

    Returns:
        WorldState: 更新後のワールド状態
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

    # プラン情報を反映
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

    # 決定スナップショットを蓄積（Kosmos解析用）
    req_id = chosen.get("request_id") or values.get("request_id") or ""
    proj.setdefault("decisions", []).append({
        "request_id": req_id,
        "ts": proj["last_decision_at"],
        "query": query,
        "chosen_title": last["chosen_title"],
        "decision_status": last["decision_status"],
        "avg_value_after": metrics["avg_value"],
        "avg_risk_after": metrics["avg_risk"],
    })

    # VERITAS全体の状態も更新
    veritas = world.setdefault("veritas", {})
    veritas["decision_count"] = int(veritas.get("decision_count", 0)) + 1
    veritas["last_risk"] = risk

    # 因果履歴に追加
    history = world.setdefault("history", {})
    decisions_hist = history.setdefault("decisions", [])

    decisions_hist.append({
        "ts": proj["last_decision_at"],
        "user_id": user_id,
        "project_id": proj.get("project_id", f"{user_id}:default"),
        "query": query,
        "chosen_id": chosen.get("id"),
        "chosen_title": last["chosen_title"],
        "gate_status": gate.get("status"),
        "gate_risk": risk,
        "value_total": val,
        "plan_steps": len(planner.get("steps", [])) if planner else 0,
    })

    # 履歴が長くなりすぎないように最新200件だけ残す
    if len(decisions_hist) > 200:
        history["decisions"] = decisions_hist[-200:]

    # ユーザー情報を記録
    meta = world.setdefault("meta", {})
    last_users = meta.setdefault("last_users", {})
    last_users[user_id] = {
        "last_seen": proj["last_decision_at"],
        "last_project": proj.get("project_id"),
    }

    _save_world(world)

    # WorldState に変換して返す
    return _project_to_worldstate(user_id, proj)


# =========================
# Public API - コンテキスト注入
# =========================

def inject_state_into_context(context: Dict[str, Any], user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    """
    決定前にコンテキストにワールド状態を注入

    Args:
        context: 既存のコンテキスト
        user_id: ユーザーID

    Returns:
        dict: 拡張されたコンテキスト
    """
    ctx = dict(context or {})
    state_data = _load_world()

    # 後方互換用: 全体stateをそのまま入れておく
    ctx["world_state"] = state_data

    # WorldStateオブジェクト
    st = load_state(user_id)

    # 基本的なワールド情報を flatten して LLＭ から参照しやすくする
    ctx.setdefault("world_state", {}).update({
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
    })

    # LLM用の軽量サマリー
    projects = state_data.get("projects", [])
    veritas_proj: Dict[str, Any] = {}

    # プロジェクトリストから veritas_agi を探す
    if isinstance(projects, list):
        for p in projects:
            if p.get("project_id") == "veritas_agi" or "veritas" in p.get("project_id", "").lower():
                veritas_proj = p
                break
    elif isinstance(projects, dict):
        veritas_proj = projects.get("veritas_agi", {})

    world_summary = {
        "projects": {
            "veritas_agi": {
                "name": veritas_proj.get("title") or veritas_proj.get("name", "VERITASのAGI化"),
                "status": veritas_proj.get("status", "unknown"),
                "progress": float(veritas_proj.get("progress", 0.0) or 0.0),
                "last_decision_ts": veritas_proj.get("last_decision_at") or veritas_proj.get("last_decision_ts"),
                "notes": veritas_proj.get("notes", ""),
                "decision_count": int(veritas_proj.get("decision_count", 0) or 0),
                "last_risk": float(veritas_proj.get("last_risk", 0.3) or 0.3),
            }
        },
    }

    # AGI 論文リサーチの軽量サマリを追加
    agi_summary = _load_memory_agi_summary(state_data)
    world_summary["external_knowledge"] = agi_summary

    ctx["world"] = world_summary

    # ユーザー情報を記録
    meta = state_data.setdefault("meta", {})
    last_users = meta.setdefault("last_users", {})
    last_users[user_id] = {
        "last_seen": _now_iso(),
        "last_project": veritas_proj.get("project_id") if veritas_proj else None,
    }
    _save_world(state_data)

    return ctx


# =========================
# Public API - シミュレーション
# =========================

def simulate(
    option: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    オプションごとのワールドシミュレーション（レガシー互換版）

    サポートする呼び出しパターン:
        simulate(option, context)
        simulate(option=..., context=..., user_id="...")
        simulate(user_id="...")  ← 古い呼び出しも許容

    Args:
        option: 評価するオプション（なければ {}）
        context: 現在のコンテキスト（なければ {}）
        user_id: （任意）状態ロード用
        **_:  余分なキーワード引数を受け取って無視（互換性のため）

    Returns:
        dict: シミュレーション結果（utility, confidence, etc.）
    """
    # デフォルト生成（古い world.simulate(user_id="...") 呼び出し対策）
    if option is None:
        option = {}
    if context is None:
        context = {}

    # まず context から world_state を拾う
    st_dict = (context or {}).get("world_state") or {}

    # context に world_state が無くて user_id が指定されている場合は、
    # load_state() から最低限の情報を構成（レガシー互換用）
    if (not st_dict) and user_id:
        st = load_state(user_id)
        st_dict = {
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

    avg_value = float(st_dict.get("avg_value", 0.5))          # 0〜1
    avg_risk = float(st_dict.get("avg_risk", 0.0))            # 0〜1
    progress = float(st_dict.get("plan_progress", 0.0))       # 0〜1

    base = float(option.get("score", 1.0))
    # 0〜1 にざっくり正規化
    base01 = _clip01(base / 2.0)

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




def simulate_decision(
    option: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    world_state: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    決定のシミュレーション（旧 world.py との互換用）

    Args:
        option: 評価するオプション（なければ {}）
        context: 現在のコンテキスト（なければ {}）
        world_state: ワールド状態（あれば context に埋め込む）
        user_id: （任意）ユーザーID
        **kwargs: その他のキーワード引数はそのまま simulate に渡す

    Returns:
        dict: シミュレーション結果
    """
    if option is None:
        option = {}
    if context is None:
        context = {}

    ctx = dict(context or {})
    if world_state:
        ctx["world_state"] = world_state

    return simulate(option=option, context=ctx, user_id=user_id, **kwargs)




# =========================
# 後方互換API
# =========================

def update_state_from_decision(
    user_id: str,
    query: str,
    chosen: dict,
    gate: dict,
) -> None:
    """後方互換用のラッパー関数"""
    update_from_decision(
        user_id=user_id,
        query=query,
        chosen=chosen,
        gate=gate,
        values={},
    )


# =========================
# Public API - VERITAS AGI Hint
# =========================

def next_hint_for_veritas_agi(user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    """
    VERITAS / AGI 用の「次にやると良い一歩」を WorldState から返す。

    - /v1/decide 内の extras["veritas_agi"] で使うことを想定
    - いまは簡易ルールベースだが、将来は Kosmos 因果モデルや
      external_knowledge を組み合わせて強化可能。
    """
    world = _load_world()
    st = load_state(user_id)

    decision_count = int(st.decisions)
    progress = float(st.progress())
    avg_value = float(st.avg_value)
    avg_risk = float(st.avg_risk)

    veritas_top = world.get("veritas", {})
    total_decisions = int(veritas_top.get("decision_count", decision_count))

    agi_summary = _load_memory_agi_summary(world)
    agi_events = int(agi_summary.get("count", 0))

    # 雑だけどわかりやすいステージ分岐
    if decision_count < 5:
        hint = "まずは /v1/decide を複数回まわして、WorldState にログを溜めるフェーズです。"
        focus = "collect_decisions"
    elif progress < 0.3:
        hint = "Planner / FUJI / ValueCore の一貫性チェックを優先してください（MVPの安定化フェーズ）。"
        focus = "stabilize_pipeline"
    elif agi_events < 1:
        hint = "少なくとも1回は AGI 関連のリサーチクエリを投げて external_knowledge を埋めると良いです。"
        focus = "seed_agi_research"
    elif progress < 0.7:
        hint = "AGI研究ログと実際の decide ログを見比べて、『どのタスクで VERITAS をベンチするか』を決める段階です。"
        focus = "design_benchmarks"
    else:
        hint = "第三者レビュー（友人・研究者）に見せる準備として、README / アーキ図 / 最小デモを整えるフェーズです。"
        focus = "external_review"

    return {
        "user_id": user_id,
        "decisions_user": decision_count,
        "decisions_total": total_decisions,
        "progress": progress,
        "avg_value": avg_value,
        "avg_risk": avg_risk,
        "agi_research_events": agi_events,
        "focus": focus,
        "hint": hint,
    }


# =========================
# エクスポート
# =========================

__all__ = [
    # データクラス
    "WorldState",
    "WorldTransition",

    # 基本操作
    "load_state",
    "save_state",
    "get_state",

    # 決定後の更新
    "update_from_decision",
    "update_state_from_decision",  # 後方互換

    # コンテキスト操作
    "inject_state_into_context",

    # シミュレーション
    "simulate",
    "simulate_decision",  # 後方互換

    # AGI hint
    "next_hint_for_veritas_agi",

    # 定数
    "DEFAULT_USER_ID",
    "WORLD_PATH",
]


