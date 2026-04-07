# VERITAS OS 全コードレビュー（2026-03-05 / Codex Agent）

## 1. レビュー範囲
- 対象: リポジトリ全体（Python バックエンド / Frontend / Packages / CI補助スクリプト）。
- 手法: 既存テストスイート実行、静的解析（ruff）、責務境界チェッカー、公開環境変数セキュリティチェッカー、手動スポット確認。
- 制約: 本レビューは「現行実装の品質・安全性検証」であり、Planner / Kernel / Fuji / MemoryOS の責務を越える設計変更は実施していない。

## 2. 実行結果サマリ
- `pytest -q`: **2697 passed / 3 skipped / 5 warnings**（失敗なし）。
- `pnpm -r test`: **全ワークスペース成功**（design-system/types/frontend 全テスト成功）。
- `ruff check .`: **All checks passed**。
- `python scripts/architecture/check_responsibility_boundaries.py`: **責務境界違反なし**。
- `python scripts/security/check_next_public_key_exposure.py`: **NEXT_PUBLIC_* の秘密情報命名違反なし**。

## 3. 主要レビュー所見

### 3.1 重大バグ（Blocker）
- 今回の実行範囲では **Blocker は未検出**。

### 3.2 品質上の注意点（Non-blocking）
1. Frontend テスト実行中に React `act(...)` 警告が出るケースがある。
   - 対象: `frontend/components/live-event-stream.test.tsx`
   - 影響: CI fail には至らないが、将来の React バージョンや strict モードで不安定化リスク。

2. JSDOM の `HTMLCanvasElement.getContext` 未実装警告がテスト時に出る。
   - 対象: `frontend/app/risk/page.test.tsx`
   - 影響: 現状はテスト通過だが、Canvas依存機能の厳密検証には `canvas` モック戦略の整備余地。

3. 一部テストで外部依存ライブラリ由来の `DeprecationWarning` / `SyntaxWarning` が観測される。
   - 影響: 直近の機能障害はないが、依存更新時の警告増加・将来的破壊的変更リスク。

## 4. セキュリティ観点（必須警告）

### 4.1 現時点の明示的な違反
- `NEXT_PUBLIC_*` への秘密情報命名パターンは検出されず、**現行ルール上の露出違反はなし**。

### 4.2 潜在リスク（警告）
- `subprocess` を利用する運用系スクリプト（例: `alert_doctor.py`, `health_check.py`, `replay_engine.py`）は、入力経路・実行パス・権限制御を誤ると攻撃面が拡大する。
- ただし `kernel.py` には実行バイナリ検証、confinement 判定、ログFDの安全オープン等の防御ロジックが存在し、一定の低減策は実装済み。

> 推奨: 運用時は
> 1) 実行ユーザー最小権限化
> 2) 監査ログ保全
> 3) subprocess 呼び出し引数の allowlist 運用
> を継続すること。

## 5. 結論
- 現行 HEAD は、テスト・静的解析・責務境界・基本的な公開変数セキュリティ検査の観点で **リリース可能水準**。
- 一方で、テスト警告（`act` / Canvas / 依存警告）は技術的負債として蓄積し得るため、次スプリントで警告ゼロ化を推奨。
