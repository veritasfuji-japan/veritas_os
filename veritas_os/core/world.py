# veritas_os/core/world.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json
import os

# === パス設定（最新版） ===
# このファイル: .../veritas_clean_test2/veritas_os/core/world.py
BASE_DIR = Path(__file__).resolve().parents[2]     # veritas_clean_test2
VERITAS_DIR = BASE_DIR / "veritas_os"

# 環境変数優先、なければ scripts/logs 下に保存
default_world_state = VERITAS_DIR / "scripts" / "logs" / "world_state.json"
WORLD_STATE_PATH = Path(os.getenv("VERITAS_WORLD_STATE", str(default_world_state)))


# ============================================================
# 基本ユーティリティ
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_memory_path() -> Path:
    """
    MemoryOS 用の memory.json のパスを推定する。

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

    return WORLD_STATE_PATH.parent / "memory.json"


# ============================================================
# AGI リサーチ用の軽量サマリ読取
# ============================================================

def _load_memory_agi_summary(state: dict) -> dict:
    """
    world_state.json 内の external_knowledge から
    AGI 論文リサーチの要約だけを取り出して、LLM 用に軽量サマリ化する。
    期待している構造:

    state["external_knowledge"] = {
        "agi_research_events": [
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
        ],
        ... (他のキーがあってもOK)
    }
    """
    try:
        ext = state.get("external_knowledge") or {}
        events = ext.get("agi_research_events") or []

        # イベントが無い / 形式がおかしい場合は空
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
        }

    except Exception as e:
        print("[world] _load_memory_agi_summary error:", e)
        return {}


def _ensure_v2_shape(state: dict) -> dict:
    """
    v1 互換を保ちつつ、因果モデル用の最低限のフィールドを保証する。
    ※ 既存 world_state.json を壊さないように「足りないキーだけ追加」する。
    """
    meta = state.setdefault("meta", {})
    meta.setdefault("version", "2.0")
    meta.setdefault("created_at", _now_iso())

    # プロジェクト・習慣
    state.setdefault("projects", {})
    state.setdefault("habits", {})

    # VERITAS 全体のトップレベル状態（因果モデル用）
    veritas = state.setdefault("veritas", {})
    veritas.setdefault("progress", 0.0)
    veritas.setdefault("decision_count", 0)
    veritas.setdefault("last_risk", 0.0)

    # 全体メトリクス
    metrics = state.setdefault("metrics", {})
    metrics.setdefault("value_ema", 0.0)
    metrics.setdefault("latency_ms_median", 0.0)
    metrics.setdefault("error_rate", 0.0)

    # 直近の遷移情報
    state.setdefault("last_transition", None)

    # 因果履歴（簡易ログ）
    history = state.setdefault("history", {})
    history.setdefault("decisions", [])

    # 外部知識（MemoryOS 等）からのサマリ領域
    state.setdefault("external_knowledge", {})

    return state


def _load_state() -> dict:
    """world_state.json を読み込む（なければデフォルト構造）"""
    try:
        if WORLD_STATE_PATH.exists():
            with WORLD_STATE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                state = _ensure_v2_shape(data)
            else:
                state = _ensure_v2_shape({})
        else:
            state = _ensure_v2_shape({})
    except Exception as e:
        print("[world] load_state error:", e)
        state = _ensure_v2_shape({})

    # ★ external_knowledge.agi_research_events から要約を作り直して agi_research に入れる
    try:
        agi_meta = _load_memory_agi_summary(state)
        if agi_meta:
            ek = state.setdefault("external_knowledge", {})
            ek["agi_research"] = agi_meta
    except Exception as e:
        print("[world] agi_research_summary merge error:", e)

    return state


def _save_state(state: dict) -> None:
    """world_state.json に保存"""
    try:
        state = _ensure_v2_shape(state)
        state.setdefault("meta", {})["updated_at"] = _now_iso()
        WORLD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with WORLD_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        # デバッグ用ログ（必ず1回はこれが出るか確認）
        print("[world] state saved ->", WORLD_STATE_PATH)
    except Exception as e:
        print("[world] save_state error:", e)


# ============================================================
# 因果モデル用クラス（状態→予測→観測→更新）
# ============================================================

@dataclass
class WorldTransition:
    """
    1 decision に対応する「予測 vs 観測」の記録
    """
    decision_id: str
    prediction: Dict[str, float]   # 例: {"delta_progress": 0.1, "delta_risk": 0.02}
    observation: Dict[str, float]  # 実測値
    error: Dict[str, float]        # observation - prediction
    decided_at: str                # ISO8601
    applied_at: Optional[str] = None


class WorldModel:
    """
    VERITAS WorldModel v2:
    - state: world_state.json の中身（_load_state/_save_state と共有）
    - predict_transition: decision 前の「期待変化」を計算
    - observe_transition: decision 後の「実測変化」を抽出
    - apply_transition: state を更新し、last_transition に記録
    """

    def __init__(self, path: Path = WORLD_STATE_PATH):
        self.path = path
        self.state: Dict[str, Any] = _load_state()

    # ---------- 基本 I/O ----------
    def save(self) -> None:
        _save_state(self.state)

    def get_state(self) -> Dict[str, Any]:
        return self.state

    # ---------- ① 予測（prediction） ----------
    def predict_transition(self, decision_payload: Dict[str, Any]) -> Dict[str, float]:
        """
        decision_payload: /v1/decide のリクエスト or FUJI/values 付きレスポンスなど。
        ここでは単純なヒューリスティックからスタート。
        """
        telos_total = (
            decision_payload.get("values", {}).get("total")
            if isinstance(decision_payload.get("values"), dict)
            else None
        )
        fuji_risk = (
            decision_payload.get("fuji", {}).get("risk")
            if isinstance(decision_payload.get("fuji"), dict)
            else None
        )

        current_progress = float(self.state.get("veritas", {}).get("progress", 0.0))
        current_risk = float(self.state.get("veritas", {}).get("last_risk", 0.0))

        # value_ema 的な「どれだけ攻めているか」をざっくり反映
        if telos_total is None:
            delta_progress = 0.0
        else:
            try:
                telos_total_f = float(telos_total)
            except Exception:
                telos_total_f = 0.5
            # 0.5 を基準に「どれだけプラスか」で progress 期待値を変える
            delta_progress = max(0.0, telos_total_f - 0.5)

        # リスクは「現在の last_risk とのズレ」を予測
        if fuji_risk is None:
            delta_risk = 0.0
        else:
            try:
                fuji_risk_f = float(fuji_risk)
            except Exception:
                fuji_risk_f = current_risk
            delta_risk = fuji_risk_f - current_risk

        return {
            "delta_progress": float(delta_progress),
            "delta_risk": float(delta_risk),
        }

    # ---------- ② 観測（observation） ----------
    def observe_transition(self, kernel_response: Dict[str, Any]) -> Dict[str, float]:
        """
        kernel_response: /v1/decide の結果 (extras.metrics / veritas_agi.snapshot / fuji.risk など)
        """
        veritas_snapshot = (
            kernel_response.get("veritas_agi", {}) or {}
        ).get("snapshot", {})

        new_progress = float(
            veritas_snapshot.get(
                "progress",
                self.state.get("veritas", {}).get("progress", 0.0),
            )
        )

        new_risk = float(
            (kernel_response.get("fuji", {}) or {}).get(
                "risk",
                self.state.get("veritas", {}).get("last_risk", 0.0),
            )
        )

        current_progress = float(self.state.get("veritas", {}).get("progress", 0.0))
        current_risk = float(self.state.get("veritas", {}).get("last_risk", 0.0))

        delta_progress = new_progress - current_progress
        delta_risk = new_risk - current_risk

        # latency 等も観測に反映（メディアンはかなり雑でOK。あとで改善）
        metrics = (kernel_response.get("extras", {}) or {}).get("metrics", {})
        latency_ms = metrics.get("latency_ms")
        if latency_ms is not None:
            try:
                self.state["metrics"]["latency_ms_median"] = float(latency_ms)
            except Exception:
                pass

        # state.veritas 側はまだここでは更新しない（apply_transition で更新）
        return {
            "delta_progress": float(delta_progress),
            "delta_risk": float(delta_risk),
        }

    # ---------- ③ 更新（update） ----------
    def apply_transition(
        self,
        decision_id: str,
        prediction: Dict[str, float],
        observation: Dict[str, float],
    ) -> WorldTransition:
        """
        prediction / observation から error を計算し、
        world_state を更新する。
        """
        current_progress = float(self.state.get("veritas", {}).get("progress", 0.0))
        current_risk = float(self.state.get("veritas", {}).get("last_risk", 0.0))
        current_decisions = int(self.state.get("veritas", {}).get("decision_count", 0))

        error = {
            key: float(observation.get(key, 0.0) - prediction.get(key, 0.0))
            for key in set(prediction) | set(observation)
        }

        # 実観測値で state を更新
        new_progress = current_progress + observation.get("delta_progress", 0.0)
        new_risk = current_risk + observation.get("delta_risk", 0.0)

        self.state["veritas"]["progress"] = float(new_progress)
        self.state["veritas"]["last_risk"] = float(new_risk)
        self.state["veritas"]["decision_count"] = current_decisions + 1

        transition = WorldTransition(
            decision_id=decision_id,
            prediction=prediction,
            observation=observation,
            error=error,
            decided_at=_now_iso(),
            applied_at=_now_iso(),
        )
        self.state["last_transition"] = asdict(transition)

        self.save()
        return transition


# ============================================================
# 既存のシンプル API（そのまま利用 or WorldModel と共存）
# ============================================================

# --- 生 state の取得・更新 ---

def get_state() -> dict:
    return _load_state()


def set_state(update: Dict[str, Any]) -> dict:
    st = _load_state()
    st.update(update)
    _save_state(st)
    return st


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
    - ctx["world"]["external_knowledge"] : AGI 論文リサーチの軽量サマリ
    """
    ctx = dict(context or {})
    state = _load_state()

    # 互換用：全体 state をそのまま入れておく
    ctx["world_state"] = state

    projects = state.get("projects", {})
    veritas_proj = projects.get("veritas_agi", {})

    # LLM 用の軽いサマリー
    world_summary = {
        "projects": {
            "veritas_agi": {
                "name": veritas_proj.get("name", "VERITASのAGI化"),
                "status": veritas_proj.get("status", "unknown"),
                "progress": float(veritas_proj.get("progress", 0.0) or 0.0),
                "last_decision_ts": veritas_proj.get("last_decision_ts"),
                "notes": veritas_proj.get("notes", ""),
                "decision_count": int(veritas_proj.get("decision_count", 0) or 0),
                "last_risk": float(veritas_proj.get("last_risk", 0.3) or 0.3),
            }
        },
    }

    # ★ AGI 論文リサーチの軽量サマリを world に混ぜる
    agi_summary = _load_memory_agi_summary(state)
    world_summary["external_knowledge"] = agi_summary

    ctx["world"] = world_summary

    # user 情報も軽くメタに刻む
    meta = state.setdefault("meta", {})
    last_users = meta.setdefault("last_users", {})
    last_users[user_id] = {
        "last_seen": _now_iso(),
        "last_project": "veritas_agi" if "veritas_agi" in projects else None,
    }
    _save_state(state)

    return ctx


# ==== 決定結果から world_state を更新（既存 API） ====
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
    now = _now_iso()

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

    # ★★★ 因果履歴（decision history）を追加 ★★★
    history = state.setdefault("history", {})
    decisions = history.setdefault("decisions", [])

    entry = {
        "ts": now,
        "user_id": user_id,
        "project_id": project_id,
        "query": query,
        "chosen_id": (chosen or {}).get("id"),
        "chosen_title": (chosen or {}).get("title"),
        "gate_status": (gate or {}).get("status"),
        "gate_risk": gate_risk,
        "value_total": proj.get("last_value_total"),
        "plan_steps": proj.get("last_plan_steps"),
    }
    decisions.append(entry)

    # 履歴が長くなりすぎないように最新200件だけ残す
    if len(decisions) > 200:
        history["decisions"] = decisions[-200:]

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


# ============================================================
# 軽量シミュレーション / スナップショット / ヒント
# ============================================================

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
    world_state.json から「VERITAS AGIプロジェクトの次の一手」を返す。

    返り値は必ず dict で、少なくとも:
      - project_id
      - phase
      - suggested_query
      - decision_count
      - progress
      - last_risk
      - external_knowledge
      - snapshot  (既存の snapshot() をそのまま利用)
    を含む。
    """
    # 現在の状態を取得
    state = _load_state()
    projects = state.get("projects") or {}
    proj = projects.get("veritas_agi") or {}

    decision_count = int(proj.get("decision_count") or 0)
    try:
        progress = float(proj.get("progress") or 0.0)
    except Exception:
        progress = 0.0
    try:
        last_risk = float(proj.get("last_risk") or 0.0)
    except Exception:
        last_risk = 0.0

    # external_knowledge（AGIリサーチの要約）
    ek = state.get("external_knowledge") or {}
    # _load_memory_agi_summary が作るサマリを優先
    agi_meta = ek.get("agi_research") or _load_memory_agi_summary(state) or {}
    ext_count = int(agi_meta.get("count") or 0)
    ext_last_query = agi_meta.get("last_query")
    ext_titles = agi_meta.get("last_titles") or []

    # ===== フェーズ判定 =====
    # decision_count と progress / ext_count からざっくりフェーズを決める
    if ext_count == 0:
        phase = "knowledge_bootstrap"
    elif decision_count < 30 or progress < 0.1:
        phase = "spec"   # AGI定義・ゴール整理フェーズ
    elif decision_count < 100 or progress < 0.4:
        phase = "arch"   # アーキテクチャ具体化フェーズ
    else:
        phase = "impl"   # 実装・検証フェーズ

    # ===== フェーズごとの suggested_query =====
    if phase == "knowledge_bootstrap":
        suggested_query = (
            "AGI定義に関する代表的な論文や定義を3つ挙げ、それぞれの観点を要約した上で、"
            "Hendrycksの定義も含めて、VERITASのAGIゴール案にどう反映すべきか提案して。"
        )
    elif phase == "spec":
        suggested_query = (
            "HendrycksのAGI定義を前提に、VERITASのAGIゴールを3フェーズ（短期/中期/長期）に分けて整理し、"
            "それぞれのフェーズで『何ができればAGIレベルと言えるか』を具体的な評価指標付きで提案して。"
        )
    elif phase == "arch":
        suggested_query = (
            "VERITASのDecision OSを、人間の仕事の大部分をループで回せる『認知OS』として設計し直す場合に、"
            "必要なモジュール構成（WorldModel/MemoryOS/Planner/Executor/ValueCore/FUJI 等）と、"
            "各モジュール間のデータフローを、図解テキストレベルで設計して。"
        )
    else:  # impl
        suggested_query = (
            "VERITASを実務レベルでAGIに近づけるために、まずどのタスク自動化（ループ実装や外部ツール統合）"
            "から着手すべきかを、優先順位付きのロードマップとして提案して。"
            "特にVERITAS開発に直結するタスクを重視して。"
        )

    # 既存の snapshot をそのまま利用（前の仕様も壊さない）
    snap = snapshot("veritas_agi")

    return {
        "project_id": "veritas_agi",
        "phase": phase,
        "suggested_query": suggested_query,
        "decision_count": decision_count,
        "progress": progress,
        "last_risk": last_risk,
        "external_knowledge": {
            "count": ext_count,
            "last_query": ext_last_query,
            "last_titles": ext_titles,
        },
        "snapshot": snap,
    }


# ============================================================
# WorldModel を外から使う用の軽いヘルパー
# ============================================================

def get_world_model() -> WorldModel:
    """
    kernel などから簡単に呼べるファクトリ。
    """
    return WorldModel()
