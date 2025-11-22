# veritas_os/core/curriculum.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from datetime import datetime

# 超簡易なインメモリ保存（とりあえず動かす用）
_USER_TASKS: Dict[str, List["CurriculumTask"]] = {}


@dataclass
class CurriculumTask:
    id: str
    title: str
    description: str
    eta_minutes: int = 30
    priority: int = 1
    tags: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_tasks(user_id: str) -> List[CurriculumTask]:
    """今日分が既に作られていれば取得。なければ空リスト。"""
    tasks = _USER_TASKS.get(user_id, [])
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return [t for t in tasks if t.id.startswith(today)]


def generate_daily_curriculum(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[CurriculumTask]:
    """
    今日やるべき “小さな3タスク” を作る。
    今は固定ロジックでOK。あとで world_state / value_ema によって
    難易度や内容を変える。
    """
    world_state = world_state or {}
    today = datetime.utcnow().strftime("%Y-%m-%d")

    tasks: List[CurriculumTask] = []

    tasks.append(
        CurriculumTask(
            id=f"{today}_plan_review",
            title="AGIプランの進捗を5分で確認",
            description="extras.planner.steps を読み直し、今日1つ進めるステップを決める。",
            eta_minutes=5,
            priority=1,
            tags=["veritas", "plan", "meta"],
        )
    )

    tasks.append(
        CurriculumTask(
            id=f"{today}_veritas_dev",
            title="VERITASコードを25分だけ触る",
            description="決めたステップに対応するコード or 設定を25分だけ進める（完璧じゃなくてOK）。",
            eta_minutes=25,
            priority=1,
            tags=["veritas", "dev", "focus"],
        )
    )

    tasks.append(
        CurriculumTask(
            id=f"{today}_health_check",
            title="短い休憩・ストレッチ",
            description="PC作業のあとに5分だけ立ち上がってストレッチか散歩をする。",
            eta_minutes=5,
            priority=2,
            tags=["health"],
        )
    )

    _USER_TASKS[user_id] = tasks
    return tasks


def plan_today(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[CurriculumTask]:
    """
    互換用：server.py から plan_today(...) を呼ばれても動くようにする。
    """
    tasks = load_tasks(user_id)
    if tasks:
        return tasks
    return generate_daily_curriculum(user_id=user_id, world_state=world_state, value_ema=value_ema)
