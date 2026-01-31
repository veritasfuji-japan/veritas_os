# run_benchmarks.py 移行ガイド

## 概要

既存の`run_benchmarks.py`と新しい拡張版の違いと移行方法を説明します。

---

## バージョン比較

| 項目 | 既存版 | 拡張版 |
|------|--------|--------|
| **ファイル名** | run_benchmarks.py | run_benchmarks_enhanced.py |
| **基本機能** | ✅ 全ベンチ実行 | ✅ 全ベンチ実行 |
| **CLI引数** | ❌ なし | ✅ あり |
| **特定ベンチ指定** | ❌ 不可 | ✅ 可能 |
| **タイムアウト設定** | ❌ なし | ✅ 可能 |
| **エラーハンドリング** | 基本的 | 詳細 |
| **code_change_plan** | ❌ なし | ✅ 自動生成 |
| **ログ** | print | logging module |
| **サマリ** | 簡易 | 詳細 |

---

## 後方互換性

拡張版は**既存版の完全な上位互換**です。

### 既存版の使い方

```bash
# 全ベンチマーク実行
python scripts/run_benchmarks.py
```

### 拡張版での同等操作

```bash
# 同じ動作
python scripts/run_benchmarks_enhanced.py

# または明示的に
python scripts/run_benchmarks_enhanced.py --all
```

**→ 既存のワークフローはそのまま動作します！**

---

## 移行手順

### オプション1: 上書き（推奨）

```bash
# バックアップ
cp scripts/run_benchmarks.py scripts/run_benchmarks.py.bak

# 拡張版で上書き
cp run_benchmarks_enhanced.py scripts/run_benchmarks.py

# 動作確認
python scripts/run_benchmarks.py --help
```

### オプション2: 並存

```bash
# 拡張版を追加
cp run_benchmarks_enhanced.py scripts/

# 既存版と拡張版を使い分け
python scripts/run_benchmarks.py              # 既存版
python scripts/run_benchmarks_enhanced.py     # 拡張版
```

---

## 新機能の使い方

### 1. 特定ベンチマークのみ実行

#### 既存版（不可）

```bash
# 全ベンチを実行するしかない
python scripts/run_benchmarks.py
```

#### 拡張版（可能）

```bash
# 1つだけ実行
python scripts/run_benchmarks_enhanced.py agi_mvp_plan.yaml

# 複数指定
python scripts/run_benchmarks_enhanced.py \
    agi_mvp_plan.yaml \
    self_evaluation_loop.yaml

# フルパスも可
python scripts/run_benchmarks_enhanced.py \
    benchmarks/agi_veritas_self_hosting.yaml
```

---

### 2. タイムアウト設定

#### 既存版（不可）

```bash
# タイムアウトなし → ハングする可能性
python scripts/run_benchmarks.py
```

#### 拡張版（可能）

```bash
# 180秒タイムアウト（デフォルト）
python scripts/run_benchmarks_enhanced.py

# カスタムタイムアウト
python scripts/run_benchmarks_enhanced.py --timeout 300

# 短いタイムアウト（テスト用）
python scripts/run_benchmarks_enhanced.py --timeout 30
```

---

### 3. code_change_plan自動生成

#### 既存版（不可）

```bash
# ベンチ実行のみ
python scripts/run_benchmarks.py

# 別途手動でタスク生成が必要
python scripts/self_heal_tasks.py --bench latest
```

#### 拡張版（可能）

```bash
# ベンチ実行 + plan生成を一度に
python scripts/run_benchmarks_enhanced.py --output-plan

# 出力例:
# logs/benchmarks/agi_mvp_plan_20250130_143022.json
# logs/benchmarks/agi_mvp_plan_plan.json  ← これが追加
```

---

### 4. 詳細ログ

#### 既存版

```bash
python scripts/run_benchmarks.py

# 出力:
# === RUN BENCH: agi_mvp_plan (...) ===
# status=200 time=15.23s
# → saved: ...
```

#### 拡張版

```bash
# 通常ログ
python scripts/run_benchmarks_enhanced.py

# 詳細ログ
python scripts/run_benchmarks_enhanced.py --verbose

# 出力:
# 2025-01-30 14:30:22 - INFO - Running: agi_mvp_plan (...)
# 2025-01-30 14:30:22 - INFO -   URL: http://127.0.0.1:8000/v1/decide
# 2025-01-30 14:30:22 - INFO -   Timeout: 180s
# 2025-01-30 14:30:37 - INFO -   Status: 200, Elapsed: 15.23s
# 2025-01-30 14:30:37 - INFO -   --- Summary ---
# 2025-01-30 14:30:37 - INFO -     Action: plan
# 2025-01-30 14:30:37 - INFO -     Telos: 0.82
# 2025-01-30 14:30:37 - INFO -     FUJI: allow
# 2025-01-30 14:30:37 - INFO -     Steps: 5
# 2025-01-30 14:30:37 - INFO -   Saved: agi_mvp_plan_20250130_143022.json
```

---

## 実用例

### 例1: 週次ベンチマーク（既存ワークフロー）

#### 既存版

```bash
#!/bin/bash
# weekly_bench.sh

python scripts/run_benchmarks.py
python scripts/bench_summary.py
```

#### 拡張版（改善）

```bash
#!/bin/bash
# weekly_bench_enhanced.sh

# 全ベンチ + plan生成
python scripts/run_benchmarks_enhanced.py --all --output-plan

# サマリ
python scripts/bench_summary.py

# タスク生成（planがあるので高速）
python scripts/self_heal_tasks.py --all-recent
```

---

### 例2: 特定機能のテスト

#### 既存版（不便）

```bash
# 1. ベンチYAMLを一時的に移動
mkdir temp_bench
mv benchmarks/*.yaml temp_bench/
mv temp_bench/agi_mvp_plan.yaml benchmarks/

# 2. 実行
python scripts/run_benchmarks.py

# 3. 元に戻す
mv temp_bench/*.yaml benchmarks/
rmdir temp_bench
```

#### 拡張版（簡単）

```bash
# 1つだけ実行
python scripts/run_benchmarks_enhanced.py agi_mvp_plan.yaml
```

---

### 例3: CI/CD統合

#### 既存版

```yaml
# .github/workflows/bench.yml
- name: Run benchmarks
  run: python scripts/run_benchmarks.py
  timeout-minutes: 60  # 全体タイムアウトのみ
```

#### 拡張版

```yaml
# .github/workflows/bench.yml
- name: Run benchmarks
  run: |
    python scripts/run_benchmarks_enhanced.py \
      --all \
      --timeout 180 \
      --output-plan
  timeout-minutes: 30  # 個別タイムアウトもあるのでより短く設定可能

- name: Check results
  run: |
    if [ $? -ne 0 ]; then
      echo "Benchmarks failed"
      exit 1
    fi
```

---

## 出力形式の変更

### JSON構造

両バージョンとも**同じJSON構造**を出力します：

```json
{
  "bench_id": "agi_mvp_plan",
  "name": "AGI MVP demo planning",
  "yaml_path": "/workspace/veritas_os/benchmarks/agi_mvp_plan.yaml",
  "request": { ... },
  "status_code": 200,
  "elapsed_sec": 15.234,
  "response_json": { ... },
  "run_at": "2025-01-30T14:30:37"  // ← 拡張版で追加（既存スクリプトに影響なし）
}
```

**→ 既存の分析スクリプト（bench_summary.py等）はそのまま動作**

---

## トラブルシューティング

### Q1: 拡張版が動かない

```bash
# 依存関係を確認
cd /workspace/veritas_os
source .venv/bin/activate
pip install requests pyyaml

# Pythonバージョン確認（3.8+必要）
python --version
```

### Q2: タイムアウトエラーが出る

```bash
# タイムアウトを延長
python scripts/run_benchmarks_enhanced.py --timeout 300

# または環境変数で設定
export VERITAS_API_BASE=http://localhost:8000
python scripts/run_benchmarks_enhanced.py
```

### Q3: 既存版に戻したい

```bash
# バックアップから復元
cp scripts/run_benchmarks.py.bak scripts/run_benchmarks.py

# または
git checkout scripts/run_benchmarks.py
```

---

## 推奨される移行パス

### フェーズ1: 並存（1週間）

```bash
# 既存版と拡張版を両方使用
python scripts/run_benchmarks.py              # 週次自動実行
python scripts/run_benchmarks_enhanced.py agi_mvp_plan.yaml  # 手動テスト
```

### フェーズ2: 段階的移行（2週間）

```bash
# 自動化スクリプトを拡張版に更新
sed -i 's/run_benchmarks.py/run_benchmarks_enhanced.py/' weekly_bench.sh

# --allオプションを明示的に追加
python scripts/run_benchmarks_enhanced.py --all
```

### フェーズ3: 完全移行（1ヶ月後）

```bash
# 既存版を削除
rm scripts/run_benchmarks.py.bak

# 拡張版をリネーム
mv scripts/run_benchmarks_enhanced.py scripts/run_benchmarks.py
```

---

## チェックリスト

### 移行前

- [ ] 既存版のバックアップ取得
- [ ] bench_summary.py等の依存スクリプト確認
- [ ] 現在のベンチ実行スクリプト確認

### 移行中

- [ ] 拡張版を並存配置
- [ ] テストベンチで動作確認
- [ ] タイムアウト設定のテスト
- [ ] code_change_plan生成のテスト

### 移行後

- [ ] 全ベンチマーク実行成功
- [ ] bench_summary.pyが正常動作
- [ ] CI/CDパイプライン更新
- [ ] ドキュメント更新

---

## まとめ

| 判断基準 | 推奨 |
|---------|------|
| 既存ワークフローを変えたくない | 拡張版で上書き（互換性あり） |
| 新機能を試したい | 拡張版を並存 |
| CI/CDで使いたい | 拡張版（タイムアウト制御が有利） |
| 特定ベンチのみテストしたい | 拡張版（必須） |

**結論**: 特別な理由がない限り、**拡張版への移行を推奨**します。

---

**作成日**: 2025年1月30日  
**バージョン**: v1.0  
**互換性**: 100%（既存版の完全上位互換）
