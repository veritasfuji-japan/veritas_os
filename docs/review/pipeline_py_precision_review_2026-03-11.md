# pipeline.py 精密レビュー（`veritas_os/core/pipeline.py`）

## 対象
- ファイル: `veritas_os/core/pipeline.py`
- レビュー観点: 責務分離、堅牢性、セキュリティ、運用リスク

## 総評
- オーケストレーション責務は概ね守られており、Planner/Kernel/FUJI/MemoryOS への委譲が明確。
- ただし、**運用時のセキュリティ/可観測性リスクが3点**あるため、優先度付きで対応を推奨。

---

## 指摘事項（優先度順）

### 1) [High][Security] Web検索失敗時のデバッグログにクエリ生値が残る
- 該当: `_safe_web_search()` の例外ログ
- 詳細: `logger.debug("_safe_web_search failed for query=%r", query, exc_info=True)` により、PII/機密情報を含む可能性があるユーザー入力クエリがログ出力されうる。
- 影響: ログ基盤への機微情報残留（監査・漏えい面でリスク）。
- 推奨:
  - `query` を `_redact_text()` でマスクしてから出力。
  - もしくはクエリ本文は出力せず request_id のみ出力。

### 2) [Medium][Security] パス上書き環境変数の境界検証不足
- 該当: `_safe_paths()`
- 詳細: `VERITAS_LOG_DIR` / `VERITAS_DATASET_DIR` を `Path(...).resolve()` でそのまま採用している。
- 影響: 誤設定または環境汚染時に、意図しないディレクトリへ監査ログ/データセットを書き出す可能性。
- 推奨:
  - 許可ベースディレクトリ（例: `REPO_ROOT` 配下）への制限。
  - もしくは明示的 allowlist と起動時バリデーションを追加。

### 3) [Medium][Reliability] `call_core_decide()` の TypeError 判定が脆い
- 該当: `_reraise_if_internal()`
- 詳細: traceback 深さ（`tb_next`）で「シグネチャ不一致」と「内部例外」を識別しているが、実装や最適化差で誤分類の余地がある。
- 影響: 実障害時に誤って別シグネチャへフォールバックし、原因追跡が遅れる可能性。
- 推奨:
  - `inspect.Signature.bind_partial()` などで呼出前検証に寄せる。
  - 失敗時の診断情報（試行パターンA/B/C・引数キー）を構造化ログ化。

---

## 良い点
- 必須/推奨/任意モジュールの import 方針が明確で、障害許容設計になっている。
- ステージ分離（inputs/retrieval/execute/policy/response/persist）が読みやすく、責務越境が少ない。
- `EVIDENCE_MAX` に上限を設け、過大メモリ消費リスクを抑制している。
- `_norm_alt()` の ID 正規化で制御文字・危険 Unicode を除去している。

## 責務境界チェック
- Planner / Kernel / Fuji / MemoryOS の実ロジックへ踏み込まず、`pipeline.py` は orchestrator として維持されている。
- 本レビューでは責務越境の改修提案は行っていない。

## 直近アクション（提案）
1. `_safe_web_search()` のログをマスク化（最優先）。
2. `_safe_paths()` に書き込み先バリデーション追加。
3. `call_core_decide()` の署名適合判定を事前検証ベースへ段階的移行。
