# VERITAS OS 全コード スパゲッティコード診断レポート（2026-02-14）

## 目的
本レビューは、リポジトリ全体（主に `veritas_os/` の本体コード）を対象に、
「責務の過密化」「長大関数」「分岐過多」「依存の密結合」を中心に、
スパゲッティコード化リスクを評価することを目的とする。

## 対象と除外
- 対象:
  - `veritas_os/**/*.py`（`tests/` は診断対象から除外）
  - 既存の設計レビュー文書を参照し、責務境界（Planner / Kernel / Fuji / MemoryOS）に沿って評価
- 除外:
  - `node_modules` などの依存物
  - 自動生成物

## 実施コマンド
1. `python -m ruff check veritas_os`
2. `python -m pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_kernel_core.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_core.py`
3. `python - <<'PY' ... AST解析で関数長・分岐数を算出 ... PY`

## 総評
- **重大な「無秩序な横断依存」の崩壊は未検出**。
- 一方で、`pipeline` / `kernel` / `fuji` 周辺に**巨大関数へ責務集中**があり、
  中長期的にはスパゲッティ化の温床になる。
- 現時点は「既に破綻」ではなく、**高リスクの前段階**。

## 主要検知（AST機械計測ベース）

### 1) 最優先: Pipeline の超巨大オーケストレーション
- `veritas_os/core/pipeline.py::run_decide_pipeline`
  - 約 2475 行
  - 分岐指標 691（AST上の制御構造カウント）
- 判断:
  - 単一関数が入力正規化・検索・計画・討論・Fuji判定・後処理を抱え込み、
    変更の影響範囲を局所化しづらい。
  - 「機能追加時に条件分岐を積み増す」構造になりやすく、典型的なスパゲッティ化リスクが高い。

### 2) 高優先: Kernel の責務過密
- `veritas_os/core/kernel.py::decide`
  - 約 806 行
  - 分岐指標 153
- 判断:
  - 実行制御・ステージ遷移・副作用処理が同居。
  - 例外系や運用オプションが増えるほど、可読性と検証容易性が低下。

### 3) 高優先: Fuji のゲート/判定ロジック膨張
- `veritas_os/core/fuji.py::fuji_core_decide`（約 275 行 / 分岐 67）
- `veritas_os/core/fuji.py::fuji_gate`（約 165 行 / 分岐 24）
- 判断:
  - ルール増加時に if/elif 連鎖が伸びる設計だと、仕様追跡コストが上がる。

### 4) 中優先: Planner / Debate / Web Search の複雑化
- `veritas_os/core/planner.py::generate_code_tasks`（約 201 行 / 分岐 59）
- `veritas_os/core/debate.py::_safe_json_extract_like`（約 165 行 / 分岐 55）
- `veritas_os/tools/web_search.py::web_search`（約 230 行 / 分岐 33）
- 判断:
  - 直ちに破綻ではないが、機能追加が続く場合は段階分解が必要。

## セキュリティ観点の警告

### ⚠️ 警告1: 外部接続処理の条件分岐増大は、検証漏れを誘発
`web_search` など外部I/O系が長大化すると、
「失敗時のフォールバック」「例外処理」「許可/拒否条件」の抜け漏れが起きやすい。

### ⚠️ 警告2: 超巨大関数は監査可能性を下げる
`run_decide_pipeline` のような巨大関数は、
セキュリティレビューで「どの入力がどこで検証されるか」を追跡しにくい。
結果として、入力検証・ログマスキング・出力制御の統制が弱くなるリスクがある。

## 責務境界（Planner / Kernel / Fuji / MemoryOS）評価
- **現状は境界そのものは維持**されている。
- ただし、オーケストレーション層で複数責務を抱え込みすぎることで、
  実装上の境界が見えづらくなっている。
- 推奨は「責務の再定義」ではなく、**同一責務内での段階分割（挙動不変リファクタ）**。

## 改善提案（境界を越えない範囲）

### A. まず 2 つの巨大関数を分割（挙動不変）
1. `pipeline.run_decide_pipeline`
   - `normalize_input` / `collect_evidence` / `run_planner` / `run_debate` / `run_fuji` / `finalize_output`
   - I/O は dataclass で明示化
2. `kernel.decide`
   - orchestration 専用に薄くし、副作用ブロックを private helper へ抽出

### B. Fuji をルールテーブル化
- if/elif 群を宣言的ルール配列に置換し、
  条件・優先度・アクションをテストしやすくする。

### C. 外部I/Oの監査容易性を改善
- `web_search` の失敗種別（timeout / 4xx / 5xx / parse）を構造化ログへ分離。
- denylist/allowlist 判定を helper 化して単体テスト可能にする。

## 結論
- 要求に対する回答: **「全体として即時に破綻したスパゲッティコードではないが、
  核となるオーケストレーション関数の肥大化が進んでおり、
  放置するとスパゲッティ化する確率が高い状態」**。
- 優先度は `pipeline` → `kernel` → `fuji` → `web_search/planner/debate` の順で、
  いずれも責務境界を越えずに改善可能。
