# veritas_os/core/experiments.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from datetime import datetime


@dataclass
class Experiment:
    id: str
    title: str
    hypothesis: str
    steps: List[str]
    expected_gain: str
    risk: float = 0.1
    tags: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def propose_experiments_for_today(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[Experiment]:
    """
    今日やるとVERITASのAGI化が一歩進む“小さな実験”を 2〜3 個返す。
    ここはまずハードコードでOK。あとで world_state / value_ema を使って賢くする。
    """
    world_state = world_state or {}
    today = datetime.utcnow().strftime("%Y-%m-%d")

    exps: List[Experiment] = []

    exps.append(
        Experiment(
            id=f"latency_check_{today}",
            title="decide のレイテンシを測る実験",
            hypothesis="ボトルネックIOを1つ潰せば体感レスポンスがかなり改善する",
            steps=[
                "3〜5回 /v1/decide を叩いて latency_ms をログから確認する",
                "平均と最大値を書き出す",
                "遅いケースの共通点（長いquery, web_search付き など）をメモ",
            ],
            expected_gain="Doctorレポートに『現在の応答速度』の事実を追加できる",
            risk=0.05,
            tags=["diagnostic", "latency", "metrics"],
        )
    )

    exps.append(
        Experiment(
            id=f"memory_hit_{today}",
            title="MemoryOS のヒット率を上げる実験",
            hypothesis="queryを8文字より少し長めに含めると、mem_hits が安定して増える",
            steps=[
                "同じテーマで wording を少し変えた decide を数回投げる",
                "extras.metrics.mem_hits の推移を見る",
                "どんなクエリだと memory_evidence_count が増えるか記録する",
            ],
            expected_gain="今後のプロンプト設計の指針が1つ増える",
            risk=0.05,
            tags=["memory", "prompt", "diagnostic"],
        )
    )

    return exps
