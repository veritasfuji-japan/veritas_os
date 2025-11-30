# AGIベンチマーク統合ガイド

## 概要

VERITAS OSのAGIベンチマークシステムと自己改善ループを完全に統合し、「ベンチ実行 → 結果分析 → タスク生成 → 実装 → 検証」のサイクルを実現します。

---

## システム構成

### コンポーネント

```
┌─────────────────────────────────────────────────────────┐
│                  AGI Benchmark System                    │
└─────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
┌─────────▼────────┐ ┌────▼────┐ ┌─────────▼──────────┐
│ run_benchmarks   │ │ bench   │ │ self_heal_tasks    │
│  _improved.py    │ │_plan.py │ │     .py            │
└──────────────────┘ └─────────┘ └────────────────────┘
          │                │                │
          │                │                │
┌─────────▼────────────────▼────────────────▼───────────┐
│            VERITAS Core (kernel / planner)             │
└────────────────────────────────────────────────────────┘
```

### ファイル構成

```
veritas_os/
├── benchmarks/                    # YAMLベンチマーク定義
│   ├── agi_veritas_self_hosting.yaml
│   ├── agi_mvp_plan.yaml
│   ├── agi_research_assistant.yaml
│   ├── self_evaluation_loop.yaml
│   ├── multi_objective_planner.yaml
│   ├── safety_boundary_test.yaml
│   └── long_horizon_roadmap.yaml
│
├── scripts/
│   ├── run_benchmarks_improved.py  # メインランナー
│   ├── self_heal_tasks.py          # タスク生成
│   ├── bench_plan.py                # 旧版（互換性維持）
│   ├── bench_summary.py             # 集計ツール
│   │
│   └── logs/
│       ├── benchmarks/              # ベンチ結果JSON
│       ├── self_heal_tasks/         # タスクプラン
│       ├── doctor_report.json       # 診断レポート
│       └── world_state.json         # 世界状態
│
└── core/
    ├── kernel.py
    ├── planner.py
    └── ...
```

---

## 使用方法

### 1. ベンチマーク実行

#### 単一ベンチマーク実行

```bash
# YAMLファイル名を指定
python scripts/run_benchmarks_improved.py agi_veritas_self_hosting.yaml

# フルパスでも可
python scripts/run_benchmarks_improved.py benchmarks/agi_mvp_plan.yaml
```

#### 全ベンチマーク実行

```bash
python scripts/run_benchmarks_improved.py --all
```

#### code_change_plan出力付き

```bash
python scripts/run_benchmarks_improved.py agi_veritas_self_hosting.yaml --output-plan
```

**出力例**:
```
scripts/logs/benchmarks/
├── agi_veritas_self_hosting_20250130_143022.json    # 結果
└── agi_veritas_self_hosting_plan.json               # タスクプラン
```

---

### 2. タスク生成

#### 最新ベンチからタスク生成

```bash
python scripts/self_heal_tasks.py --bench latest
```

#### 特定ベンチからタスク生成

```bash
python scripts/self_heal_tasks.py --bench agi_veritas_self_hosting_20250130_143022.json
```

#### 過去24時間の全ベンチから統合タスク生成

```bash
python scripts/self_heal_tasks.py --all-recent
```

#### Markdown形式で出力

```bash
python scripts/self_heal_tasks.py --bench latest --format markdown
```

**出力例**:
```json
{
  "meta": {
    "generated_at": "2025-01-30T14:35:22",
    "bench_count": 1,
    "doctor_issues_count": 2,
    "world_progress": 0.0,
    "world_decision_count": 0
  },
  "tasks": [
    {
      "id": "task_001",
      "type": "doc",
      "priority": 2,
      "title": "世界モデルと安全境界の言語化",
      "description": "現実的な制約付きAGI研究の世界モデルを言語化...",
      "target_module": "docs",
      "target_path": "world_model.md",
      "risk": "medium",
      "impact": "high",
      "source": "bench:agi_veritas_self_hosting",
      "tasks": [
        "現在の利用環境を文章で整理する",
        "代表的な失敗モードを3〜7件列挙",
        "FUJI Gateのチェック条件を定義"
      ],
      "artifacts": ["world_model.md", "failure_modes_and_fuji_spec.md"],
      "done_criteria": [...]
    }
  ],
  "summary": {
    "total_tasks": 7,
    "by_type": {"doc": 5, "code_change": 2},
    "by_priority": {"1": 1, "2": 3, "3": 3},
    "high_risk_count": 0,
    "high_impact_count": 5
  }
}
```

---

### 3. 集計・分析

#### ベンチ結果サマリ

```bash
python scripts/bench_summary.py
```

**出力例**:
```
=== VERITAS Bench Summary ===
対象ディレクトリ: /path/to/logs/benchmarks
集計日時: 2025-01-30 14:40:00

[agi_veritas_self_hosting] VERITAS self-hosting AGI research OS design
  実行回数        : 3
  200 OK          : 3 / 3
  decision_status : {'allow': 2, 'modify': 1}
  平均 elapsed    : 15.234 sec
  平均 telos_score: 0.812
  FUJI 分布       : {'allow': 2, 'modify': 1}
  --- WorldModel / Tasks ---
  最新 progress   : 0.0
  累計 decision   : 0
  tasks 件数      : 5
```

---

## ワークフロー

### 完全な自己改善サイクル

```bash
# ステップ1: ベンチマーク実行
python scripts/run_benchmarks_improved.py --all --output-plan

# ステップ2: タスク生成
python scripts/self_heal_tasks.py --all-recent --format json

# ステップ3: タスクレビュー（人間）
cat scripts/logs/self_heal_tasks/self_heal_tasks_20250130_144500.json

# ステップ4: 実装（手動またはVERITAS支援）
# ... タスクに従ってコード修正 ...

# ステップ5: 再度ベンチマーク実行（検証）
python scripts/run_benchmarks_improved.py agi_veritas_self_hosting.yaml

# ステップ6: 結果比較
python scripts/bench_summary.py
```

### 週次メンテナンスループ

```bash
#!/bin/bash
# weekly_self_improve.sh

echo "=== Weekly VERITAS Self-Improvement Loop ==="

# 1. 全ベンチマーク実行
echo "[1/4] Running all benchmarks..."
python scripts/run_benchmarks_improved.py --all --output-plan

# 2. タスク生成
echo "[2/4] Generating tasks..."
python scripts/self_heal_tasks.py --all-recent --format markdown

# 3. サマリ出力
echo "[3/4] Summary..."
python scripts/bench_summary.py

# 4. 人間レビュー用ファイル一覧
echo "[4/4] Review these files:"
ls -lht scripts/logs/self_heal_tasks/ | head -5

echo "=== Complete ==="
```

---

## ベンチマーク一覧と目的

### 現在利用可能なベンチマーク

| Bench ID | 目的 | 時間 | 難易度 |
|----------|------|------|--------|
| **agi_veritas_self_hosting** | 自己改善ループ全体設計 | ~30s | ⭐⭐⭐⭐⭐ |
| **agi_mvp_plan** | MVP デモ計画 | ~15s | ⭐⭐⭐ |
| **agi_research_assistant** | リサーチアシスタント設計 | ~20s | ⭐⭐⭐⭐ |
| **self_evaluation_loop** | 週次評価ループ設計 | ~20s | ⭐⭐⭐⭐ |
| **multi_objective_planner** | 多目的最適化 | ~15s | ⭐⭐⭐ |
| **safety_boundary_test** | 安全境界テスト | ~15s | ⭐⭐⭐ |
| **long_horizon_roadmap** | 6ヶ月ロードマップ | ~25s | ⭐⭐⭐⭐ |

### ベンチマークの選び方

**初回セットアップ**:
```bash
# 1. まずMVPから
python scripts/run_benchmarks_improved.py agi_mvp_plan.yaml

# 2. 次に安全境界を確認
python scripts/run_benchmarks_improved.py safety_boundary_test.yaml

# 3. 最後に自己改善設計
python scripts/run_benchmarks_improved.py agi_veritas_self_hosting.yaml
```

**定期メンテナンス**:
```bash
# 週次: 自己評価 + ロードマップ
python scripts/run_benchmarks_improved.py \
    self_evaluation_loop.yaml \
    long_horizon_roadmap.yaml

# 月次: 全ベンチマーク
python scripts/run_benchmarks_improved.py --all
```

---

## 出力形式

### ベンチマーク結果 JSON

```json
{
  "bench_id": "agi_veritas_self_hosting",
  "name": "VERITAS self-hosting AGI research OS design",
  "status_code": 200,
  "elapsed_sec": 18.234,
  "request": { ... },
  "response_json": {
    "chosen": {
      "title": "自己改善ループ設計",
      "action": "plan",
      "rationale": "..."
    },
    "fuji": {
      "status": "allow",
      "risk_score": 0.15
    },
    "telos_score": 0.82,
    "extras": {
      "planner": {
        "steps": [
          {
            "id": "step1",
            "title": "世界モデルと安全境界の言語化",
            "objective": "...",
            "tasks": [...],
            "artifacts": ["world_model.md"],
            "metrics": [...],
            "risks": [...],
            "done_criteria": [...]
          }
        ]
      }
    }
  },
  "error": null,
  "run_at": "2025-01-30T14:30:22.123456"
}
```

### タスクプラン JSON

```json
{
  "meta": {
    "generated_at": "2025-01-30T14:35:00",
    "bench_count": 1,
    "doctor_issues_count": 2,
    "world_progress": 0.0
  },
  "tasks": [
    {
      "id": "task_001",
      "type": "doc",
      "priority": 2,
      "title": "世界モデルと安全境界の言語化",
      "target_module": "docs",
      "target_path": "world_model.md",
      "risk": "medium",
      "impact": "high",
      "source": "bench:agi_veritas_self_hosting",
      "tasks": [...],
      "artifacts": [...],
      "done_criteria": [...]
    }
  ],
  "summary": {
    "total_tasks": 5,
    "by_type": {"doc": 3, "code_change": 2},
    "high_risk_count": 0
  }
}
```

---

## カスタマイズ

### 新しいベンチマーク追加

1. **YAMLファイル作成**

```yaml
# benchmarks/my_custom_bench.yaml
id: "my_custom_bench"
name: "My Custom Benchmark"
description: "Custom test for specific feature"

request:
  context:
    user_id: "benchmark_user"
    mode: "agi_framework"
    goals:
      - "Test specific AGI capability"
    time_horizon: "short"
    
  query: "Specific task description..."
  
  options: []
  stream: false
```

2. **実行**

```bash
python scripts/run_benchmarks_improved.py my_custom_bench.yaml
```

### タスク優先度調整

`self_heal_tasks.py`の`_calc_priority()`関数を編集:

```python
def _calc_priority(change: Dict[str, Any]) -> int:
    """優先度を計算（カスタマイズ例）"""
    risk = change.get("risk", "medium")
    impact = change.get("impact", "medium")
    
    # プロジェクト固有のルール
    if "critical" in change.get("title", "").lower():
        return 1  # 最優先
    
    # デフォルトロジック
    if risk == "high" and impact == "high":
        return 1
    # ...
```

---

## トラブルシューティング

### 問題1: ベンチマークがタイムアウト

```bash
# タイムアウトを延長
python scripts/run_benchmarks_improved.py agi_veritas_self_hosting.yaml --timeout 300
```

### 問題2: APIサーバーに接続できない

```bash
# APIサーバーが起動しているか確認
curl http://127.0.0.1:8000/health

# ポートを変更
export VERITAS_API_BASE=http://localhost:8080
python scripts/run_benchmarks_improved.py ...
```

### 問題3: タスクが生成されない

```bash
# ベンチ結果を確認
cat scripts/logs/benchmarks/agi_veritas_self_hosting_20250130_143022.json | jq '.response_json.extras.planner.steps'

# ログを確認
python scripts/self_heal_tasks.py --bench latest 2>&1 | grep -i error
```

### 問題4: 結果JSONが壊れている

```bash
# JSONバリデーション
cat scripts/logs/benchmarks/latest.json | python -m json.tool

# 手動で修正してから処理
python scripts/self_heal_tasks.py --bench fixed_bench.json
```

---

## 統計とメトリクス

### ベンチマーク成功率

```bash
# 過去7日間の成功率
find scripts/logs/benchmarks -name "*.json" -mtime -7 | \
    xargs python -c "
import json, sys
total = 0
success = 0
for f in sys.argv[1:]:
    with open(f) as fp:
        data = json.load(fp)
        total += 1
        if data.get('status_code') == 200:
            success += 1
print(f'Success rate: {success}/{total} ({success/total*100:.1f}%)')
" {}
```

### 平均実行時間

```bash
# bench_id ごとの平均実行時間
python -c "
import json, glob
from collections import defaultdict

times = defaultdict(list)
for f in glob.glob('scripts/logs/benchmarks/*.json'):
    with open(f) as fp:
        data = json.load(fp)
        bench_id = data.get('bench_id', 'unknown')
        elapsed = data.get('elapsed_sec', 0)
        times[bench_id].append(elapsed)

for bench_id, ts in sorted(times.items()):
    avg = sum(ts) / len(ts)
    print(f'{bench_id:30s}: {avg:6.2f}s (n={len(ts)})')
"
```

---

## ベストプラクティス

### 1. 定期的なベンチマーク実行

```bash
# cron設定例（毎週月曜 9:00）
0 9 * * 1 cd /path/to/veritas_os && python scripts/run_benchmarks_improved.py --all
```

### 2. Gitとの統合

```bash
# ベンチ前にブランチ作成
git checkout -b bench/weekly-$(date +%Y%m%d)

# ベンチ実行
python scripts/run_benchmarks_improved.py --all

# 結果をコミット
git add scripts/logs/benchmarks/
git commit -m "Weekly benchmark results $(date +%Y-%m-%d)"
```

### 3. タスク管理との統合

```bash
# GitHub Issues作成（gh CLI使用）
python scripts/self_heal_tasks.py --bench latest --format markdown > tasks.md

cat tasks.md | gh issue create --title "Weekly self-heal tasks" --body-file -
```

---

## 次のステップ

現在の実装で完了した機能:
- ✅ ベンチマーク実行基盤
- ✅ 結果のJSON保存
- ✅ code_change_plan生成
- ✅ タスク優先度付け
- ✅ doctor_report連携

今後の拡張候補:
- ⏳ 自動コード生成（タスク → PR）
- ⏳ メトリクス可視化ダッシュボード
- ⏳ A/Bテスト（異なる設定での比較）
- ⏳ 継続的改善ループの自動化
- ⏳ 外部評価者によるブラインドテスト

---

**作成日**: 2025年1月  
**バージョン**: v1.0  
**作成者**: Claude (Anthropic)
