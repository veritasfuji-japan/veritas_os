# veritas/core/world.py
from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any, Dict
import os

# === パス設定（最新版） ===
# このファイル: .../veritas_clean_test2/veritas_os/core/world.py
BASE_DIR = Path(__file__).resolve().parents[2]     # veritas_clean_test2
VERITAS_DIR = BASE_DIR / "veritas_os"

# 環境変数優先、なければ scripts/logs 下に保存
default_world_state = VERITAS_DIR / "scripts" / "logs" / "world_state.json"
WORLD_STATE_PATH = Path(os.getenv("VERITAS_WORLD_STATE", str(default_world_state)))


# === 基本ヘルパー ===
def _load_state() -> dict:
    """world_state.json を読み込む（なければデフォルト構造）"""
    try:
        if WORLD_STATE_PATH.exists():
            with WORLD_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print("[world] load_state error:", e)

    # デフォルト骨格
    return {
        "projects": {},
        "habits": {},
        "meta": {
            "version": "1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _save_state(state: dict) -> None:
    """world_state.json に保存"""
    try:
        WORLD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with WORLD_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[world] save_state error:", e)


# === 公開 API ===
def get_state() -> dict:
    return _load_state()


def set_state(update: Dict[str, Any]) -> dict:
    st = _load_state()
    st.update(update)
    _save_state(st)
    return st


def _save_state(state: dict) -> None:
    """world_state.json に保存"""
    try:
        WORLD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with WORLD_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        # デバッグ用ログ（必ず1回はこれが出るか確認）
        print("[world] state saved ->", WORLD_STATE_PATH)
    except Exception as e:
        print("[world] save_state error:", e)


def _ensure_project(state: dict, pid: str, name: str) -> dict:
    """projects[pid] がなければ初期化して返す"""
    projects = state.setdefault("projects", {})
    proj = projects.get(pid)
    if not isinstance(proj, dict):
        proj = {
            "name": name,
            "status": "in_progress",
            "progress": 0.0,
            "last_decision_ts": None,
            "last_query": None,
            "last_gate_status": None,
            "last_value_total": None,
            "last_plan_steps": 0,
            "decision_count": 0,
            "last_risk": 0.3,
            "last_latency_ms": None,
            "notes": "",
        }
        projects[pid] = proj
    return proj


# ==== context への注入 ====
def inject_state_into_context(context: dict, user_id: str) -> dict:
    """
    決定前に /v1/decide の context に世界状態を混ぜる。

    - ctx["world_state"] : 生の world_state（後方互換用）
    - ctx["world"]       : LLM が読みやすい要約（projects など）
    """
    ctx = dict(context or {})
    state = _load_state()

    # 互換用：全体 state をそのまま入れておく
    ctx["world_state"] = state

    projects = state.get("projects", {})
    veritas = projects.get("veritas_agi", {})

    # LLM 用の軽いサマリー
    world_summary = {
        "projects": {
            "veritas_agi": {
                "name": veritas.get("name", "VERITASのAGI化"),
                "status": veritas.get("status", "unknown"),
                "progress": float(veritas.get("progress", 0.0) or 0.0),
                "last_decision_ts": veritas.get("last_decision_ts"),
                "notes": veritas.get("notes", ""),
                "decision_count": int(veritas.get("decision_count", 0) or 0),
                "last_risk": float(veritas.get("last_risk", 0.3) or 0.3),
            }
        }
    }

    ctx["world"] = world_summary

    # user 情報も軽くメタに刻む
    meta = state.setdefault("meta", {})
    last_users = meta.setdefault("last_users", {})
    last_users[user_id] = {
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "last_project": "veritas_agi" if "veritas_agi" in projects else None,
    }
    _save_state(state)

    return ctx


# ==== 決定結果から world_state を更新（新しい正式API） ====
def update_from_decision(
    *,
    user_id: str,
    query: str,
    chosen: dict,
    gate: dict,
    values: dict | None = None,
    planner: dict | None = None,
    latency_ms: int | None = None,
) -> None:
    """
    /v1/decide の結果から world_state を更新する。
    ★ 今は「VERITASのAGI化」プロジェクトに無条件で積み上げる（絶対更新用）。
    """
    state = _load_state()
    now = datetime.now(timezone.utc).isoformat()

    # ここでは query 内容に関係なく、必ず veritas_agi に記録する
    project_id = "veritas_agi"
    proj = _ensure_project(state, project_id, "VERITASのAGI化")

    proj["status"] = "in_progress"
    proj["last_decision_ts"] = now
    proj["last_query"] = query
    proj["last_gate_status"] = (gate or {}).get("status")

    if isinstance(values, dict):
        try:
            proj["last_value_total"] = float(values.get("total", 0.0))
        except Exception:
            proj["last_value_total"] = None

    proj["decision_count"] = int(proj.get("decision_count") or 0) + 1

    # planner からステップ数などを反映
    if isinstance(planner, dict):
        steps = planner.get("steps") or []
        if isinstance(steps, list):
            proj["last_plan_steps"] = len(steps)

            # 超ざっくり：プランが通るたびに progress を少しずつ上げる
            prev = float(proj.get("progress") or 0.0)
            proj["progress"] = min(1.0, round(prev + 0.02, 3))

            if steps:
                titles = [st.get("title") or st.get("name") or "" for st in steps]
                proj["notes"] = " / ".join([t for t in titles[:5] if t])

    # gate の risk なども反映
    try:
        gate_risk = float((gate or {}).get("risk", 0.0))
    except Exception:
        gate_risk = 0.0
    proj["last_risk"] = gate_risk

    if latency_ms is not None:
        try:
            proj["last_latency_ms"] = int(latency_ms)
        except Exception:
            proj["last_latency_ms"] = None

    # user 情報を meta に記録
    meta = state.setdefault("meta", {})
    last_users = meta.setdefault("last_users", {})
    last_users[user_id] = {
        "last_seen": now,
        "last_project": project_id,
    }

    _save_state(state)


# ==== 後方互換ラッパー（既存コードが使っているかもしれない） ====
def update_state_from_decision(user_id: str, query: str, chosen: dict, gate: dict):
    """
    旧版互換のための薄いラッパー。
    新しい update_from_decision を簡易パラメータで呼ぶ。
    """
    update_from_decision(
        user_id=user_id,
        query=query,
        chosen=chosen,
        gate=gate,
        values=None,
        planner=None,
        latency_ms=None,
    )


# ==== 軽量シミュレーション API ====
def simulate(user_id: str, query: str, chosen: dict | None = None) -> dict:
    """
    AGI 化ステップ2: 世界モデルの簡易シミュレーション。

    - 現在の progress / risk を読み出し、
      「このクエリを実行したら progress がどれだけ伸びそうか」を
      ごく簡単なルールで推定する。
    """
    state = _load_state()
    projects = state.get("projects", {})
    proj = projects.get("veritas_agi", {})

    current_progress = float(proj.get("progress", 0.0))
    current_risk = float(proj.get("last_risk", 0.3))

    try:
        if isinstance(query, str):
            q_raw = query
        else:
            q_raw = json.dumps(query, ensure_ascii=False)
    except Exception:
        q_raw = str(query)

    q = q_raw.lower()

    # 超ざっくりなヒューリスティック
    delta = 0.0
    if any(k in q for k in ["plan", "ステップ", "実装", "行程表"]):
        delta = 0.02
    elif any(k in q for k in ["構想", "アイデア", "design", "設計"]):
        delta = 0.01

    predicted_progress = min(1.0, round(current_progress + delta, 3))
    predicted_risk = max(0.0, min(1.0, round(current_risk * 0.98, 3)))

    return {
        "predicted_progress": predicted_progress,
        "predicted_risk": predicted_risk,
        "base_progress": current_progress,
        "base_risk": current_risk,
        "note": "world.simulate() heuristic prediction",
    }


def snapshot(project_id: str = "veritas_agi") -> dict:
    """
    world_state.json から指定プロジェクトの状態だけを取り出す軽いヘルパー。
    decide 以外（CLI や DASH）からも再利用できるようにしておく。
    """
    state = _load_state()
    proj = (state.get("projects") or {}).get(project_id) or {}
    try:
        progress = float(proj.get("progress", 0.0))
    except Exception:
        progress = 0.0

    return {
        "id": project_id,
        "name": proj.get("name", "VERITASのAGI化"),
        "status": proj.get("status", "unknown"),
        "progress": progress,
        "decision_count": int(proj.get("decision_count") or 0),
        "last_risk": float(proj.get("last_risk", 0.0) or 0.0),
        "last_decision_ts": proj.get("last_decision_ts"),
        "notes": proj.get("notes", ""),
    }


def next_hint_for_veritas_agi() -> dict:
    """
    現在の progress / decision_count から、
    「次にやるべき一手」をざっくり決めて返す。
    実装が進んだら、ここをどんどん賢くしていく。
    """
    snap = snapshot("veritas_agi")
    p = snap["progress"]
    n = snap["decision_count"]

    # progress と回数に応じてステージ分け（超ざっくり版）
    if p < 0.05:
        hint = "まずは README と全体アーキテクチャ図を1枚にまとめる（人に説明できる形にする）。"
    elif p < 0.15:
        hint = "MemoryOS・WorldModel・ValueCore・TrustOS の関係を図解してドキュメント化する。"
    elif p < 0.25:
        hint = "Swagger の各エンドポイントに説明文を追記して、VERITAS API を『人に渡せる』状態にする。"
    elif p < 0.35:
        hint = "決定ログから 3〜5 件ピックして、良かった/微妙だった例を分析するスクリプトを作る。"
    elif p < 0.5:
        hint = "world_state.json と value_core.json をもとに、次のプランを自動で微調整するロジックを小さく1個入れる。"
    elif p < 0.7:
        hint = "VERITAS を使った具体的ユースケース（労働紛争、自分の音楽プロジェクト等）を1つ決めて、専用テンプレを作る。"
    elif p < 0.9:
        hint = "外部のLLM(API)とつなぐインターフェースを設計し、『自分以外でも回せる』形に整理する。"
    else:
        hint = "AGI化MVPとしてのデモ動画・技術レポートをまとめて、第三者レビューをもらうフェーズ。"

    meta_msg = f"決定ログ: {n}件, progress: {p:.3f}, last_risk: {snap['last_risk']:.3f}"

    return {
        "snapshot": snap,
        "hint": hint,
        "meta": meta_msg,
    }    
