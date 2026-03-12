# pipeline.py 精密レビュー（`veritas_os/core/pipeline.py`）

## 対象
- ファイル: `veritas_os/core/pipeline.py`
- レビュー観点: 責務分離、堅牢性、セキュリティ、運用リスク
- 更新日: 2026-03-12

## 総評
- オーケストレーション責務は維持されており、Planner / Kernel / FUJI / MemoryOS への委譲境界は明確。
- 先行レビューで挙げた主要懸念（ログ漏えい、パス境界、呼び出しシグネチャ判定）は、**概ね対策済み**。
- 追加の運用強化として、失敗時ログの機微情報露出をさらに下げる改善を推奨。

---

## 指摘事項（優先度順 / 現状評価つき）

### 1) [High][Security] Web検索失敗ログの機微情報露出
- 該当: `_safe_web_search()` の例外ログ
- 現状:
  - クエリ本文は `_redact_text()` でマスクされるため、**平文漏えいリスクは低減済み**。
  - さらに、問い合わせ識別のために `query_sha256_12`（SHA-256先頭12桁）を併記すると、本文を残さず障害追跡しやすい。
- 推奨（改善済み方針）:
  - `query_redacted` + `query_sha256_12` の構造でログ化。
  - 可能なら request_id（または trace_id）との紐づけを統一。

### 2) [Medium][Security] パス上書き環境変数の境界検証
- 該当: `_safe_paths()`
- 現状:
  - `VERITAS_LOG_DIR` / `VERITAS_DATASET_DIR` は、既定で `REPO_ROOT` 配下のみ許容。
  - `VERITAS_ALLOW_EXTERNAL_PATHS=1` 時のみ明示的に外部パスを許可。
  - 監査観点では、拒否ログに生の入力値を残しすぎない設計が望ましい。
- 推奨（改善済み方針）:
  - 警告ログの候補パスを `_redact_text()` でマスク。
  - 起動時に「外部パス許可中」の明示ログを出し、運用監査しやすくする。

### 3) [Medium][Reliability] `call_core_decide()` の TypeError 判定
- 該当: `call_core_decide()`
- 現状:
  - `inspect.Signature.bind_partial()` による事前適合判定へ移行済みで、traceback 深さ依存より堅牢。
  - A/B/C の試行診断がログ化され、フォールバック挙動の説明可能性が向上。
- 残課題（軽微）:
  - 署名検査不能時の `except Exception` は可用性優先のため許容だが、将来的には例外種別を絞る余地あり。

---

## 良い点
- 必須/推奨/任意モジュールの import 方針が明確で、障害許容設計になっている。
- ステージ分離（inputs/retrieval/execute/policy/response/persist）が読みやすく、責務越境が少ない。
- `EVIDENCE_MAX` に上限を設け、過大メモリ消費リスクを抑制している。
- `_norm_alt()` の ID 正規化で制御文字・危険 Unicode を除去している。

## 責務境界チェック
- Planner / Kernel / Fuji / MemoryOS の実ロジックへ踏み込まず、`pipeline.py` は orchestrator として維持。
- 本レビューの改善案も、pipeline 層の入力防御・ログ衛生・運用可観測性に限定。

## セキュリティ警告（運用）
- `VERITAS_ALLOW_EXTERNAL_PATHS=1` は監査ログ/データセットの書き込み先を外部に開放するため、**本番では原則無効**を推奨。
- デバッグログを本番で有効化する場合、PII マスキング規約と保持期間を必ず運用手順に明記すること。

## 直近アクション（提案）
1. `_safe_web_search()` 失敗ログを `query_redacted + query_sha256_12` 形式へ統一。
2. `_safe_paths()` の拒否ログで候補パスをマスクし、監査漏えいリスクを低減。
3. `VERITAS_ALLOW_EXTERNAL_PATHS=1` の利用時に起動警告を追加（任意）。
