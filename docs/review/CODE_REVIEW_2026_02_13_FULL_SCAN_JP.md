# VERITAS OS 全体コードレビュー（2026-02-13）

## 実施範囲
- Python 実装（`veritas_os/` 配下）を対象にレビュー。
- 既存の大量生成物/依存物（例: `node_modules`）は除外。
- 重点: Planner / Kernel / Fuji / MemoryOS の責務境界を壊さない改善案。

## 実行したチェック（抜粋）
1. `python -m ruff check veritas_os`
2. `pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_kernel_core.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_core.py`
3. `rg -n "(eval\(|exec\(|subprocess\.|os\.system\(|shell=True|pickle\.load|yaml\.load\()" veritas_os`
4. AST ベースで長大関数を計測（120行以上を抽出）

---

## 総評
- **品質は高い**。lint は通過し、Planner / Kernel / Fuji / MemoryOS の代表テストは通過。
- 一方で、**長大関数への集中**と、**外部接続まわりの防御（SSRF/TLS運用）**は、将来の保守性・安全性の観点で優先改善が必要。

---

## 優先度A（高）

### A-1. `run_decide_pipeline` の分割（保守性リスク）
- 対象: `veritas_os/core/pipeline.py` の `run_decide_pipeline`（約 2400 行）。
- 問題:
  - 単一関数に責務が集中し、変更時の副作用範囲が広い。
  - レビュー/デバッグ/テスト設計が難化。
- 改善案:
  - ステージ単位で関数抽出（input normalizer / evidence / planner / debate / fuji / post-process）。
  - ステージごとに dataclass で I/O 契約を固定。
  - 既存公開 API を維持する facade として `run_decide_pipeline` を残す。

### A-2. `kernel.decide` の orchestration 専用化
- 対象: `veritas_os/core/kernel.py` の `decide`（約 800 行）。
- 問題:
  - 実行制御、doctor 起動、world update、実験提案などが密結合。
- 改善案:
  - `decide` を「薄いオーケストレータ」にし、
    `doctor_runner.py` / `world_updater.py` / `daily_experiments.py` へ分割。
  - 依存注入（DI）でテスト時に副作用を差し替え可能に。

### A-3. Web 検索の SSRF 防御を「スキーム検証のみ」から強化
- 対象: `veritas_os/tools/web_search.py`
- 現状:
  - `VERITAS_WEBSEARCH_URL` のスキーム検証は実装済み（良い）。
- 懸念:
  - 内部IP/localhost/metadata endpoint への到達を完全には防ぎきれない。
- 改善案:
  - URL ホストを allowlist 化（例: 明示許可ドメインのみ）。
  - `127.0.0.0/8`, `10.0.0.0/8`, `169.254.169.254` 等を拒否。
  - 必要に応じ DNS rebinding 耐性（解決後IPの再検証）を追加。

> ⚠️ **セキュリティ警告**: 外部接続設定が環境変数に依存するため、CI/CD や運用環境の設定ミスで SSRF 面が再露出する余地があります。

---

## 優先度B（中）

### B-1. `fuji_core_decide` / `fuji_gate` のルールテーブル化
- 対象: `veritas_os/core/fuji.py`
- 問題:
  - 条件分岐が増えるほど挙動追跡が困難。
- 改善案:
  - ルールを declarative なテーブル（優先度・条件・アクション）に移管。
  - ルールセットに対するパラメトリックテストを追加。

### B-2. `build_report` の段階分解と I/O 境界明確化
- 対象: `veritas_os/scripts/generate_report.py`
- 問題:
  - 生成処理・集計・入出力が同一関数に混在。
- 改善案:
  - `collect -> aggregate -> render -> write` の4段へ分割。
  - 各段の pure function 化で回帰テストを軽量化。

### B-3. `web_search` のリトライ戦略の観測性改善
- 対象: `veritas_os/tools/web_search.py`
- 問題:
  - リトライはあるが、運用での失敗傾向分析に必要なメトリクスが不足。
- 改善案:
  - 失敗要因（timeout/DNS/429/5xx）を構造化ログで出力。
  - circuit breaker 的な連続失敗抑制を導入。

---

## 優先度C（低〜中）

### C-1. scripts 群の HTTP/TLS 運用ガード
- 対象: `veritas_os/scripts/decide_plan.py` など
- 懸念:
  - デフォルト `http://127.0.0.1` はローカル用途として妥当だが、
    リモート運用時に HTTPS 強制が弱い。
- 改善案:
  - 非ローカル URL を検出したら HTTPS を必須化（警告→失敗）。

### C-2. 大規模関数の段階的テスト拡張
- 改善案:
  - planner / fuji / kernel / memory の境界をまたがない形で
    「1ステージ1テストモジュール」へ整理。
  - 失敗時の原因切り分け速度を向上。

---

## 責務境界に関する評価
- 現状、Planner / Kernel / Fuji / MemoryOS は概ね分離されている。
- ただし長大関数によって **見かけ上の境界が曖昧化** しているため、
  「機能追加ではなく分割リファクタ」を優先すると安全。

---

## すぐ着手できる改善バックログ（提案）
1. `pipeline.run_decide_pipeline` を 6〜8 関数へ分割（挙動不変）。
2. `kernel.decide` の doctor 実行部を専用モジュールへ抽出。
3. `web_search` に host allowlist + private IP deny を導入。
4. `generate_report.build_report` を4段分解。
5. 上記 1〜4 それぞれに回帰テストを追加。

