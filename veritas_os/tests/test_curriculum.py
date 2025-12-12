# veritas_os/tests/test_curriculum.py

from datetime import datetime, timezone
from typing import Dict, Any

import veritas_os.core.curriculum as curriculum
from veritas_os.core.curriculum import CurriculumTask


def _today_prefix() -> str:
    # UTC の「今日」文字列（本体側と揃える）
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _reset_user_tasks():
    # グローバル状態を毎テスト前にクリア
    curriculum._USER_TASKS.clear()  # type: ignore[attr-defined]


# ------------------------------
# CurriculumTask / load_tasks
# ------------------------------

def test_curriculum_task_to_dict_and_load_tasks_filters_by_today():
    _reset_user_tasks()
    user_id = "user123"
    today = _today_prefix()

    # 今日分と、過去日付分を混ぜて突っ込む
    t_today = CurriculumTask(
        id=f"{today}_plan_review",
        title="today task",
        description="do something today",
    )
    t_old = CurriculumTask(
        id="2000-01-01_old",
        title="old task",
        description="should not be returned",
    )

    curriculum._USER_TASKS[user_id] = [t_today, t_old]  # type: ignore[attr-defined]

    tasks = curriculum.load_tasks(user_id)
    # 過去日付分はフィルタされる
    assert len(tasks) == 1
    assert tasks[0].id.startswith(today)

    # to_dict も確認しておく
    as_dict = tasks[0].to_dict()
    assert as_dict["id"] == t_today.id
    assert as_dict["title"] == t_today.title
    assert as_dict["description"] == t_today.description
    # デフォルト値もちゃんと入っていること
    assert as_dict["eta_minutes"] == 30
    assert as_dict["priority"] == 1


# ------------------------------
# _stage_from_world
# ------------------------------

def test_stage_from_world_progress_ranges_and_fallbacks():
    _reset_user_tasks()

    def s(world: Dict[str, Any] | None) -> str:
        return curriculum._stage_from_world(world)  # type: ignore[attr-defined]

    # None / 不正値 → 0.0 扱いで S1
    assert s(None) == "S1_bootstrap"
    assert s({"veritas": {"progress": "not-a-number"}}) == "S1_bootstrap"

    # 各レンジの境界チェック
    assert s({"veritas": {"progress": 0.0}}) == "S1_bootstrap"
    assert s({"veritas": {"progress": 0.05}}) == "S1_bootstrap"

    assert s({"veritas": {"progress": 0.10}}) == "S2_arch"
    assert s({"veritas": {"progress": 0.20}}) == "S2_arch"

    assert s({"veritas": {"progress": 0.25}}) == "S3_api"
    assert s({"veritas": {"progress": 0.40}}) == "S3_api"

    assert s({"veritas": {"progress": 0.45}}) == "S4_analytics"
    assert s({"veritas": {"progress": 0.64}}) == "S4_analytics"

    assert s({"veritas": {"progress": 0.65}}) == "S5_usecase"
    assert s({"veritas": {"progress": 0.84}}) == "S5_usecase"

    assert s({"veritas": {"progress": 0.85}}) == "S6_review"
    assert s({"veritas": {"progress": 0.95}}) == "S6_review"

    # veritas_agi 側からも取れること
    assert s({"veritas_agi": {"progress": 0.3}}) == "S3_api"


# ------------------------------
# generate_daily_curriculum
# ------------------------------

def test_generate_daily_curriculum_s1_default_value_ema_mid():
    """
    S1/S2 ステージ + value_ema=0.5 の基本パターン。
    """
    _reset_user_tasks()
    user_id = "u1"

    tasks = curriculum.generate_daily_curriculum(
        user_id=user_id,
        world_state={"veritas": {"progress": 0.05}},  # S1_bootstrap
        value_ema=0.5,
    )

    today = _today_prefix()
    assert len(tasks) == 3

    # すべて今日の日付プレフィックス
    for t in tasks:
        assert t.id.startswith(today)

    # 1つ目: メタプラン確認タスク
    t0 = tasks[0]
    assert t0.id.endswith("_plan_review")
    assert "AGIプランの進捗" in t0.title
    assert t0.eta_minutes == 5
    assert "veritas" in (t0.tags or [])

    # 2つ目: S1/S2 用の README / アーキテクチャ更新タスク
    t1 = tasks[1]
    assert t1.id.endswith("_veritas_core")
    assert "README / アーキテクチャ図" in t1.title
    assert t1.eta_minutes == 25  # value_ema=0.5 → デフォルト 25
    assert "design" in (t1.tags or [])
    assert "doc" in (t1.tags or [])

    # 3つ目: 振り返りメモ（value_ema=0.5 → reflection側）
    t2 = tasks[2]
    assert t2.id.endswith("_health_reflect")
    assert "短い振り返りメモを書く" in t2.title
    assert t2.eta_minutes == 5
    assert "health" in (t2.tags or [])
    assert "reflection" in (t2.tags or [])

    # _USER_TASKS にも保存されている
    assert user_id in curriculum._USER_TASKS  # type: ignore[attr-defined]
    assert len(curriculum._USER_TASKS[user_id]) == 3  # type: ignore[attr-defined]


def test_generate_daily_curriculum_s5_usecase_and_value_ema_low():
    """
    S5/S6 ステージ + value_ema 低いときの分岐。
    """
    _reset_user_tasks()
    user_id = "u2"

    tasks = curriculum.generate_daily_curriculum(
        user_id=user_id,
        world_state={"veritas": {"progress": 0.9}},  # S6_review 相当
        value_ema=0.2,  # 低い → dev 15分 / health はストレッチ系
    )

    assert len(tasks) == 3

    t1 = tasks[1]
    # S5/S6 用の「実ユースケースで /v1/decide」タスク
    assert "実ユースケースで /v1/decide を2〜3回回す" in t1.title
    assert t1.eta_minutes == 15  # value_ema < 0.3 → 15
    assert "usecase" in (t1.tags or [])

    t2 = tasks[2]
    # value_ema < 0.4 → 休憩タスク
    assert "5〜10分の休憩・ストレッチ" in t2.title
    assert t2.eta_minutes == 10


def test_generate_daily_curriculum_value_ema_high():
    """
    value_ema 高いときは dev_minutes が 30 になる。
    """
    _reset_user_tasks()
    user_id = "u3"

    tasks = curriculum.generate_daily_curriculum(
        user_id=user_id,
        world_state={"veritas": {"progress": 0.3}},  # S3_api
        value_ema=0.8,
    )

    assert len(tasks) == 3
    t1 = tasks[1]
    # S3/S4 用タイトルになっていること
    assert "VERITASコード or ログ分析を25分だけ進める" in t1.title
    assert t1.eta_minutes == 30  # value_ema > 0.7 → 30

    t2 = tasks[2]
    # value_ema >= 0.4 → 振り返りメモ側
    assert "短い振り返りメモを書く" in t2.title
    assert t2.eta_minutes == 5


# ------------------------------
# plan_today
# ------------------------------

def test_plan_today_generates_once_and_reuses():
    """
    plan_today:
      - 最初の呼び出しで generate_daily_curriculum を叩く
      - 2回目以降は既存タスクをそのまま返す（world_state が変わっても）
    """
    _reset_user_tasks()
    user_id = "u_plan"

    # 1回目: S1
    tasks1 = curriculum.plan_today(
        user_id=user_id,
        world_state={"veritas": {"progress": 0.05}},
        value_ema=0.5,
    )
    assert len(tasks1) == 3

    # world_state を変えても、既存タスクがそのまま返る
    tasks2 = curriculum.plan_today(
        user_id=user_id,
        world_state={"veritas": {"progress": 0.9}},
        value_ema=0.1,
    )

    # オブジェクトが同一である必要はないが、id セットは変わらないはず
    ids1 = [t.id for t in tasks1]
    ids2 = [t.id for t in tasks2]
    assert ids1 == ids2

    # _USER_TASKS も変わらず3件
    assert user_id in curriculum._USER_TASKS  # type: ignore[attr-defined]
    assert len(curriculum._USER_TASKS[user_id]) == 3  # type: ignore[attr-defined]


