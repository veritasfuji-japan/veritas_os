# veritas_os/core/experiments.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from veritas_os.core.time_utils import utc_now


@dataclass
class Experiment:
    """
    「VERITAS のAGI化を一歩進める小さな実験」1件分。
    - id:  日付なども含めた一意ID
    - title: 実験タイトル
    - hypothesis: 何が良くなると仮定しているか
    - steps: 実験の具体ステップ（1〜5個程度）
    - expected_gain: うまくいった時に何が得られるか
    - risk: 0.0〜1.0 での主観的リスク
    - tags: 分類用のタグ
    """
    id: str
    title: str
    hypothesis: str
    steps: List[str]
    expected_gain: str
    risk: float = 0.1
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def propose_experiments_for_today(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[Experiment]:
    """
    今日やると VERITAS の AGI 化が一歩進む “小さな実験” を 2〜3 個返す。

    - world_state.progress が低いほど「ブートストラップ寄り」の実験を返す
    - progress が上がると、MemoryOS / FUJI / WorldModel 連携など少し高度な実験を混ぜる
    - value_ema が低いときはリスク低め、高いときは少し攻めた実験も混ざる
    """
    world_state = world_state or {}
    today = utc_now().strftime("%Y-%m-%d")

    veritas = (world_state.get("veritas") or world_state.get("veritas_agi") or {}) or {}
    progress = float(veritas.get("progress", 0.0) or 0.0)
    decision_count = int(veritas.get("decision_count", 0) or 0)

    exps: List[Experiment] = []

    # ---- 共通で有効な “診断系” 実験 ----
    exps.append(
        Experiment(
            id=f"latency_check_{today}",
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
        )
    )

    exps.append(
        Experiment(
            id=f"memory_hit_{today}",
            title="MemoryOS のヒット率を上げる実験",
            hypothesis="同じテーマで wording をそろえると mem_hits と memory_evidence_count が安定して増える",
            steps=[
                "同じテーマ（例: VERITAS開発）で wording を少し変えた decide を 5 回投げる",
                "各レスポンスの extras.metrics.mem_hits / memory_evidence_count をメモする",
                "どんなクエリだと memory_evidence_count が増えるか、良いパターンを 3 つ箇条書きにする",
            ],
            expected_gain="今後のプロンプト設計の指針が1つ増え、MemoryOS の価値が上がる",
            risk=0.05,
            tags=["memory", "prompt", "diagnostic"],
        )
    )

    # ---- progress に応じて追加する実験 ----

    if progress < 0.15:
        # S1〜S2: とにかく「状態を正しく持つ」ことに集中
        exps.append(
            Experiment(
                id=f"world_progress_{today}",
                title="WorldModel の progress / decision_count を確認する実験",
                hypothesis="world_state が正しく更新されていれば、AGIループは壊れにくくなる",
                steps=[
                    "2〜3回 /v1/decide を通常クエリで実行する",
                    "scripts/logs/world_state.json を開き veritas.progress / decision_count の推移を見る",
                    "数値の変化をメモし、『更新されていない箇所』があれば doctor_report の TODO に書く",
                ],
                expected_gain="WorldModel の生き死にをすぐ確認できる手順が1つ確立する",
                risk=0.05,
                tags=["world", "state", "bootstrap"],
            )
        )
    elif progress < 0.4:
        # S3〜S4: FUJI / Planner / Debate の品質を軽く見るフェーズ
        exps.append(
            Experiment(
                id=f"fuji_risk_tune_{today}",
                title="FUJI Gate のリスク値を軽くキャリブレーションする実験",
                hypothesis="stakes を変えると gate_risk / effective_risk が意味のある変化をする",
                steps=[
                    "同じ query で stakes を低・中・高の 3 パターンにして /v1/decide を叩く",
                    "extras.fuji.gate_risk / effective_risk を比較する",
                    "直感とズレているケースがあれば doctor_report に『FUJI調整候補』として1行メモする",
                ],
                expected_gain="FUJI Gate の挙動理解が深まり、安全設定の今後のチューニング指針ができる",
                risk=0.1,
                tags=["fuji", "safety", "diagnostic"],
            )
        )
    else:
        # S5 以降: 実ユースケース × ループ運用実験
        exps.append(
            Experiment(
                id=f"usecase_loop_{today}",
                title="1つの実ユースケースで連続ループ運用してみる実験",
                hypothesis="同じユースケースに 3〜5 回連続で decide を回すと、World / Memory / Value がうまく溜まってくる",
                steps=[
                    "対象ユースケースを1つ決める（例: 労働紛争 or 音楽制作など）",
                    "同じテーマで 3〜5 回連続で /v1/decide を実行する",
                    "各回の extras.veritas_agi.hint / world_state.progress / value_ema の変化をメモする",
                ],
                expected_gain="『実際の人間のプロジェクト』を VERITAS ループに乗せたときの挙動が見える",
                risk=0.15,
                tags=["loop", "usecase", "world", "memory"],
            )
        )

    # value_ema がかなり高いときは、少し攻めた実験のリスクを上げる（まだ単純な調整）
    if value_ema > 0.7:
        for e in exps:
            if e.risk < 0.15:
                e.risk = min(0.2, e.risk + 0.05)

    return exps
