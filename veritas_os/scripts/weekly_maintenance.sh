#!/bin/bash
echo "=== VERITAS Weekly Maintenance ==="
date

# ベンチマーク実行
python scripts/run_benchmarks_enhanced.py --all --output-plan

# タスク生成
python scripts/self_heal_tasks.py --all-recent --format markdown > WEEKLY_TASKS.md

# サマリ表示
python scripts/bench_summary.py

echo ""
echo "✅ Maintenance complete!"
echo "📋 Tasks: WEEKLY_TASKS.md"
echo "📊 Logs: scripts/logs/"
