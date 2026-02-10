# veritas_os/core/curriculum.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

# 超簡易なインメモリ保存（とりあえず動かす用）
# ★ メモリリーク防止: ユーザー数の上限を設ける
_MAX_USERS = 1000
_USER_TASKS: Dict[str, List["CurriculumTask"]] = {}


@dataclass
class CurriculumTask:
    """
    「今日やる小さなタスク」1件分。
    - id: 日付プレフィックス + 種別 など
    - title: タイトル（UI に出す用）
    - description: 具体的に何をするか
    - eta_minutes: 所要時間めやす（分）
    - priority: 1 が最優先。数字が大きいほど低優先。
    - tags: 分類用タグ（"veritas", "health" など）
    """
    id: str
    title: str
    description: str
    eta_minutes: int = 30
    priority: int = 1
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _today_str() -> str:
    """UTCベースの今日の日付を YYYY-MM-DD 文字列で返す（tz-aware版）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_tasks(user_id: str) -> List[CurriculumTask]:
    """
    今日分が既に作られていれば取得。なければ空リスト。
    - 実ストレージは後で差し替え前提。今はインメモリ。
    """
    tasks = _USER_TASKS.get(user_id, [])
    today = _today_str()
    return [t for t in tasks if t.id.startswith(today)]


def _stage_from_world(world_state: Dict[str, Any] | None) -> str:
    """
    world_state からざっくりステージを推定。
    experiments.py の _infer_veritas_stage と合わせてもOK。
    """
    ws = world_state or {}
    veritas = (ws.get("veritas") or ws.get("veritas_agi") or {}) or {}
    try:
        p = float(veritas.get("progress", 0.0) or 0.0)
    except Exception:
        p = 0.0

    if p < 0.10:
        return "S1_bootstrap"
    elif p < 0.25:
        return "S2_arch"
    elif p < 0.45:
        return "S3_api"
    elif p < 0.65:
        return "S4_analytics"
    elif p < 0.85:
        return "S5_usecase"
    else:
        return "S6_review"


def generate_daily_curriculum(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[CurriculumTask]:
    """
    今日やるべき “小さな 3 タスク” を作る。

    - world_state.progress から VERITAS のステージを推定し、内容を変える
    - value_ema が低い時は「メンテ・健康・負荷低め」寄り
      高い時は「開発・実験」寄りに少しシフト
    """
    today = _today_str()
    stage = _stage_from_world(world_state)

    tasks: List[CurriculumTask] = []

    # 1. メタ・プラン確認（全ステージ共通）
    tasks.append(
        CurriculumTask(
            id=f"{today}_plan_review",
            title="AGIプランの進捗を5分で確認",
            description=(
                "最新の /v1/decide レスポンス（extras.planner.steps や chosen）を1つ開き、"
                "『今日中に1ステップだけ進めるならどれか』を決めてメモする。"
            ),
            eta_minutes=5,
            priority=1,
            tags=["veritas", "plan", "meta"],
        )
    )

    # 2. ステージに応じてメイン開発タスクを切り替え
    if stage in ("S1_bootstrap", "S2_arch"):
        dev_title = "README / アーキテクチャ図を10〜20分だけ更新"
        dev_desc = (
            "VERITAS の現在の構成（kernel / planner / debate / memory / world / fuji など）を確認し、"
            "README や設計メモを 10〜20分だけ更新する。"
            "新しく実装したモジュールやフローがあれば1行でも良いので追記する。"
        )
        tags = ["veritas", "design", "doc"]
    elif stage in ("S3_api", "S4_analytics"):
        dev_title = "VERITASコード or ログ分析を25分だけ進める"
        dev_desc = (
            "決めたステップに対応するコード修正、もしくは logs/decide_*.json 等の分析を 25 分だけ進める。"
            "完了させる必要はなく、『どこまで進んだか』を1行メモに残す。"
        )
        tags = ["veritas", "dev", "analytics"]
    else:  # S5_usecase, S6_review
        dev_title = "実ユースケースで /v1/decide を2〜3回回す"
        dev_desc = (
            "労働紛争 or 音楽制作など、1つの実ユースケースを選び、"
            "そのテーマで /v1/decide を2〜3回実行する。"
            "それぞれの chosen.title と extras.veritas_agi.hint をメモし、"
            "『次回から定例で回したいクエリ』を1つ書き出す。"
        )
        tags = ["veritas", "usecase", "loop"]

    dev_minutes = 25
    if value_ema < 0.3:
        # ちょっと疲れ気味 → 時間を短く
        dev_minutes = 15
    elif value_ema > 0.7:
        # 調子が良い → 少し長めにコミット
        dev_minutes = 30

    tasks.append(
        CurriculumTask(
            id=f"{today}_veritas_core",
            title=dev_title,
            description=dev_desc,
            eta_minutes=dev_minutes,
            priority=1,
            tags=tags,
        )
    )

    # 3. ヘルス / リフレクション系タスク
    if value_ema < 0.4:
        # メンタル・体力ケアを優先
        health_title = "5〜10分の休憩・ストレッチ"
        health_desc = (
            "PC から一度離れて 5〜10 分だけ立ち上がり、ストレッチをするか外の空気を吸う。"
            "『今日 VERITAS で進んだことを1つ』心の中で振り返る。"
        )
        eta = 10
    else:
        health_title = "短い振り返りメモを書く"
        health_desc = (
            "今日の作業が終わったタイミングで 5 分だけ取り、"
            "・今日進んだこと\n・気づいたボトルネック\n・明日やりたい1ステップ\n"
            "をテキストファイルかメモアプリに書き出す。"
        )
        eta = 5

    tasks.append(
        CurriculumTask(
            id=f"{today}_health_reflect",
            title=health_title,
            description=health_desc,
            eta_minutes=eta,
            priority=2,
            tags=["health", "reflection"],
        )
    )

    # ★ メモリリーク防止: ユーザー数上限を超えたら最古のエントリを削除（FIFO方式）
    if len(_USER_TASKS) >= _MAX_USERS and user_id not in _USER_TASKS:
        oldest_key = next(iter(_USER_TASKS))
        del _USER_TASKS[oldest_key]
    _USER_TASKS[user_id] = tasks
    return tasks


def plan_today(
    user_id: str,
    world_state: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
) -> List[CurriculumTask]:
    """
    後方互換: server.py などから plan_today(...) を呼ばれても動くようにする。
    - 既に今日分があればそれを返し、なければ生成。
    """
    tasks = load_tasks(user_id)
    if tasks:
        return tasks
    return generate_daily_curriculum(
        user_id=user_id,
        world_state=world_state,
        value_ema=value_ema,
    )

