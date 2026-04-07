# VERITAS OS 詳細コードレビュー（Agent版 / 2026-02-13）

## 1. 目的
本レビューは、`veritas_os/` 配下の実装について、
**Planner / Kernel / Fuji / MemoryOS の責務境界を維持したまま**、
保守性・信頼性・セキュリティを改善するための実行可能な提案をまとめたものです。

---

## 2. 対象範囲と前提
- 対象: Python 実装（`veritas_os/`）
- 除外: 生成物・外部依存ディレクトリ（例: `node_modules`）
- 重点観点:
  1. 責務分離（Planner / Kernel / Fuji / MemoryOS）
  2. セキュリティ（特に外部接続・入力処理）
  3. 長大関数による変更波及リスク

---

## 3. 実施チェック（再現用）
1. `python -m ruff check veritas_os`
2. `pytest -q veritas_os/tests/test_planner.py veritas_os/tests/test_kernel_core.py veritas_os/tests/test_fuji_core.py veritas_os/tests/test_memory_core.py`
3. `rg -n "(eval\(|exec\(|subprocess\.|os\.system\(|shell=True|pickle\.load|yaml\.load\()" veritas_os`
4. AST ベースの長大関数計測（120行以上抽出）

---

## 4. エグゼクティブサマリ
- 現状品質は高く、主要 lint/test は通過可能な構成。
- 一方で、以下を優先して手当てしない場合、将来の変更失敗率が上がる。
  - 長大関数への責務集中
  - Web 接続境界の防御不足（SSRF、TLS 運用）

> ⚠️ **セキュリティ警告**
> 外部接続先が環境変数に依存する実装は、設定逸脱時に SSRF 面が再露出する可能性があります。
> 「コード側での拒否制御」を必須化し、運用設定の正しさだけに依存しない設計にしてください。

---

## 5. 優先度A（高）

### A-1. `pipeline.run_decide_pipeline` の分割（最優先）
- 対象: `veritas_os/core/pipeline.py`
- 課題:
  - 約 2400 行規模の単一関数に責務が集中。
  - 影響範囲推定・レビュー・段階テストが困難。
- 改善:
  - `normalize_input` / `collect_evidence` / `plan` / `debate` / `fuji_gate` / `post_process` へ抽出。
  - ステージ間 I/O を dataclass で契約化。
  - 既存公開 API は `run_decide_pipeline` を facade として維持。
- 完了条件:
  - 既存シグネチャ不変。
  - 主要回帰テスト green。
  - ステージ単位のユニットテスト追加。

### A-2. `kernel.decide` のオーケストレーション専用化
- 対象: `veritas_os/core/kernel.py`
- 課題:
  - doctor 実行、world 更新、実験提案等が 1 関数に密結合。
- 改善:
  - `doctor_runner.py` / `world_updater.py` / `daily_experiments.py` へ抽出。
  - DI（依存注入）で副作用を差し替え可能にし、テスト容易性を上げる。
- 完了条件:
  - `decide` は「順序制御と集約」のみを担当。
  - 既存 API 互換維持。

### A-3. `web_search` の SSRF 防御強化
- 対象: `veritas_os/tools/web_search.py`
- 現状:
  - URL スキーム検証は実装済み。
- 課題:
  - private IP / localhost / metadata endpoint 防御が不十分。
- 改善:
  - host allowlist 導入（明示許可ドメインのみ）。
  - denylist: `127.0.0.0/8`, `10.0.0.0/8`, `169.254.169.254` 等。
  - DNS rebinding 対策として「名前解決後 IP の再検証」を追加。
- 完了条件:
  - 危険宛先のテストケースで明示的に reject。
  - ログに拒否理由（構造化）を出力。

---

## 6. 優先度B（中）

### B-1. `fuji` 判定ロジックのルールテーブル化
- 対象: `veritas_os/core/fuji.py`
- 改善:
  - 条件分岐を宣言的ルール（優先度・条件・アクション）へ移管。
  - パラメトリックテストで回帰を固定。

### B-2. `build_report` の4段分割
- 対象: `veritas_os/scripts/generate_report.py`
- 改善:
  - `collect -> aggregate -> render -> write` へ分割。
  - pure function 比率を上げ、差分検証を容易化。

### B-3. `web_search` リトライの可観測性強化
- 対象: `veritas_os/tools/web_search.py`
- 改善:
  - timeout/DNS/429/5xx を分類して構造化ログ化。
  - 連続失敗時の circuit breaker 導入。

---

## 7. 優先度C（低〜中）

### C-1. scripts の TLS 運用ガード
- 対象: `veritas_os/scripts/decide_plan.py` など
- 改善:
  - 非ローカル URL は HTTPS 必須（警告だけでなく失敗させる）。

### C-2. 境界単位のテスト再編
- 改善:
  - planner / kernel / fuji / memory の境界を越えない形で
    「1ステージ1テストモジュール」に整理。

---

## 8. 責務境界の適合性評価
- Planner / Kernel / Fuji / MemoryOS の分離は概ね維持されている。
- ただし、長大関数により実装レベルで境界が見えづらくなっている。
- 推奨方針:
  - 新機能追加より先に、**挙動不変の分割リファクタ**を優先。
  - 境界を越える共通化（安易なユーティリティ化）は禁止。

---

## 9. 30日アクションプラン（提案）
1. Week 1: `run_decide_pipeline` のステージ抽出設計とテスト雛形。
2. Week 2: `kernel.decide` の副作用分離 + DI 化。
3. Week 3: `web_search` の allowlist/denylist + DNS 再検証。
4. Week 4: `generate_report` 分割、回帰テスト整備、運用ログ改善。

KPI（最小）:
- 120 行超関数数の削減
- セキュリティ拒否ケースのテスト追加数
- 失敗原因の分類可能率（ログ）

---

## 10. 結論
優先順位は明確です。
1) 長大関数の分割で保守性を回復し、
2) Web 接続境界の防御をコードで強制し、
3) 観測性を高めて運用事故の検知を早める。

この順で進めれば、責務境界を保ったまま安全に改善できます。
