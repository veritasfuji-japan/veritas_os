# veritas_os/core/experiments.py
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# =========================================================
# Time helpers (local; avoid core.time_utils import hazards)
# =========================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# Helpers
# =========================================================

def _clip01(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _stable_id(prefix: str, today: str, user_id: str, *parts: str) -> str:
    """
    その日の同じ入力からは同じIDが出る（再実行で増殖しない）安定ID。
    """
    seed = "|".join([prefix, today, user_id, *[p for p in parts if p]])
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{today}_{h}"


def _get_veritas_bucket(world_state: Dict[str, Any]) -> Dict[str, Any]:
    # 互換: veritas / veritas_agi のどちらでも良い
    v = world_state.get("veritas_agi")
    if isinstance(v, dict) and v:
        return v
    v2 = world_state.get("veritas")
    if isinstance(v2, dict) and v2:
        return v2
    return {}


def _stage(progress: float) -> str:
    if progress < 0.15:
        return "bootstrap"
    if progress < 0.40:
        return "calibration"
    return "loop"


# =========================================================
# Data model
# =========================================================

@dataclass
class Experiment:
    """
    「VERITAS のAGI化を一歩進める小さな実験」1件分。

    - id: 一意ID（推奨: 日付+ハッシュ）
    - title: 実験タイトル
    - hypothesis: 何が良くなると仮定しているか
    - steps: 実験の具体ステップ（1〜5個程度推奨）
    - expected_gain: うまくいった時に何が得られるか
    - risk: 0.0〜1.0 の主観リスク
    - tags: 分類タグ
    - meta: 任意メタ（stage / knobs / notes など）
    - created_at: 生成時刻（UTC）
    """

    id: str
    title: str
    hypothesis: str
    steps: List[str]
    expected_gain: str
    risk: float = 0.1
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: utc_now().isoformat())

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.hypothesis = (self.hypothesis or "").strip()
        self.expected_gain = (self.expected_gain or "").strip()

        # steps を正規化（空行除去）
        norm_steps: List[str] = []
        for s in self.steps or []:
            s2 = str(s).strip()
            if s2:
                norm_steps.append(s2)
        self.steps = norm_steps or ["(steps missing)"]

        # risk クリップ
        self.risk = _clip01(self.risk, default=0.1)

        # tags 正規化
        if self.tags is None:
            self.tags = []
        self.tags = [str(t).strip() for t in self.tags if str(t).strip()]

        if not self.id:
            # 最低限のフォールバック（ただし propose_* 側で安定IDを作るのが本筋）
            today = utc_now().strftime("%Y-%m-%d")
            self.id = _stable_id("exp", today, "anon", self.title)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =========================================================
# Main API
# =========================================================

def propose_experiments_for_today(
    user_id: str,
    world_state: Optional[Dict[str, Any]] = None,
    value_ema: float = 0.5,
) -> List[Experiment]:
    """
    今日やると VERITAS の AGI 化が一歩進む “小さな実験” を返す（基本 3件）。

    ポリシー:
    - progress が低い: 状態更新/ログ整合/最小ループの“生存確認”
    - progress 中: FUJI/Planner/Debate のキャリブレーション
    - progress 高: 実ユースケース連続ループ（World/Memory/Value の蓄積を見る）
    - value_ema が低い: リスク低め寄り / 高い: 少し攻める（ただし上限は守る）
    """
    ws = world_state or {}
    today = utc_now().strftime("%Y-%m-%d")

    v = _get_veritas_bucket(ws)
    progress = _clip01(v.get("progress", 0.0), default=0.0)
    decision_count = _to_int(v.get("decision_count", 0), default=0)
    stage = _stage(progress)

    # 返す件数（環境変数で調整可）
    try:
        target_n = int(os.getenv("VERITAS_EXPERIMENTS_PER_DAY", "3"))
    except Exception:
        target_n = 3
    target_n = max(2, min(6, target_n))

    val = _clip01(value_ema, default=0.5)

    exps: List[Experiment] = []

    # ---- 共通で効く “診断系” ----
    exps.append(
        Experiment(
            id=_stable_id("latency_check", today, user_id, stage),
            title="decide のレイテンシを測る実験",
            hypothesis="ボトルネックIOを1つ潰せば体感レスポンスがかなり改善する",
            steps=[
                "3〜5回 /v1/decide を叩いて extras.metrics.latency_ms をログから確認する",
                "平均と最大値を書き出す（メモ or doctor_report に追記）",
                "遅いケースの共通点（長い query / web_search 付き など）をメモする",
            ],
            expected_gain="Doctorレポートに『現在の応答速度』の事実を追加でき、今後の最適化ポイントが見える",
            risk=0.05,
            tags=["diagnostic", "latency", "metrics"],
            meta={"stage": stage, "progress": progress, "decision_count": decision_count},
        )
    )

    exps.append(
        Experiment(
            id=_stable_id("memory_hit", today, user_id, stage),
            title="MemoryOS のヒット率を上げる実験",
            hypothesis="同じテーマで wording をそろえると mem_hits と mem_evidence_count が安定して増える",
            steps=[
                "同じテーマ（例: VERITAS開発）で wording を少し変えた decide を 5 回投げる",
                "各レスポンスの extras.metrics.mem_hits / mem_evidence_count をメモする",
                "どんなクエリだと mem_evidence_count が増えるか、良いパターンを 3 つ箇条書きにする",
            ],
            expected_gain="今後のプロンプト設計の指針が1つ増え、MemoryOS の価値が上がる",
            risk=0.05,
            tags=["memory", "prompt", "diagnostic"],
            meta={"stage": stage, "progress": progress, "decision_count": decision_count},
        )
    )

    # ---- stage別の “前進系” ----
    if stage == "bootstrap":
        exps.append(
            Experiment(
                id=_stable_id("world_progress", today, user_id, str(decision_count)),
                title="WorldModel の progress / decision_count を確認する実験",
                hypothesis="world_state が正しく更新されていれば、AGIループは壊れにくくなる",
                steps=[
                    "2〜3回 /v1/decide を通常クエリで実行する",
                    "world_state.json（または保存先）を開き veritas.progress / decision_count の推移を見る",
                    "数値が増えない場合、update_from_decision の入力（planner/gate/values）をログで確認する",
                ],
                expected_gain="WorldModel の生き死にをすぐ確認できる手順が1つ確立する",
                risk=0.05,
                tags=["world", "state", "bootstrap"],
                meta={"stage": stage, "progress": progress, "decision_count": decision_count},
            )
        )
    elif stage == "calibration":
        exps.append(
            Experiment(
                id=_stable_id("fuji_risk_tune", today, user_id, str(round(val, 3))),
                title="FUJI Gate のリスク値を軽くキャリブレーションする実験",
                hypothesis="stakes を変えると gate_risk / effective_risk が意味のある変化をする",
                steps=[
                    "同じ query で stakes を低・中・高の 3 パターンにして /v1/decide を叩く",
                    "gate.risk / extras.metrics.effective_risk（ある場合）/ fuji.risk を比較する",
                    "直感とズレるケースがあれば『FUJI調整候補』として1行メモする",
                ],
                expected_gain="FUJI Gate の挙動理解が深まり、安全設定のチューニング指針ができる",
                risk=0.10,
                tags=["fuji", "safety", "diagnostic"],
                meta={"stage": stage, "progress": progress, "decision_count": decision_count},
            )
        )
    else:
        exps.append(
            Experiment(
                id=_stable_id("usecase_loop", today, user_id, str(decision_count)),
                title="1つの実ユースケースで連続ループ運用してみる実験",
                hypothesis="同じユースケースに 3〜5 回連続で decide を回すと、World / Memory / Value が溜まって質が上がる",
                steps=[
                    "対象ユースケースを1つ決める（例: 労働紛争 / 音楽制作 / VERITAS開発）",
                    "同じテーマで 3〜5 回連続で /v1/decide を実行する",
                    "各回の world_state.progress / mem_evidence_count / value_ema（あれば）をメモする",
                ],
                expected_gain="『実際の人間のプロジェクト』を VERITAS ループに乗せた時の挙動が見える",
                risk=0.15,
                tags=["loop", "usecase", "world", "memory"],
                meta={"stage": stage, "progress": progress, "decision_count": decision_count},
            )
        )

    # ---- value_ema による “攻め/守り” 微調整（上限は守る） ----
    # 低い: さらに慎重 / 高い: 少し攻める
    if val < 0.40:
        for e in exps:
            e.risk = _clip01(e.risk * 0.85, default=e.risk)
    elif val > 0.70:
        for e in exps:
            # ★FIX: 条件を < 0.15 に固定（指定）
            if e.risk < 0.15:
                e.risk = min(0.22, e.risk + 0.05)

    # ---- 返却数調整（優先度: 低リスク→実験価値） ----
    # まず risk 昇順、次に title で安定ソート
    exps.sort(key=lambda x: (x.risk, x.title))

    # target_n に揃える（最低2、最大6）
    return exps[:target_n]


