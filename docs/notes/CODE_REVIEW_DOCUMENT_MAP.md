# コードレビュー文書マップ（整理版）

最終更新: 2026-02-16

この文書は、リポジトリ内に点在しているコードレビュー関連 Markdown の
**参照順序**と**用途**を整理するためのインデックスです。

---

## 1. まず最初に見る文書（現行の正）

1. `docs/review/CODE_REVIEW_STATUS.md`
   - 修正進捗の追跡（Fix/Deferred/Accepted）
   - 実装対応の最新状態を把握する基準
2. `docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md`
   - 実行可能な範囲での最新ランタイム確認結果
   - 環境依存で未実施の項目も明示

> 運用上は、上記 2 ファイルを「一次情報」として扱います。

---

## 2. 参照目的別の読み分け

### A. 直近の包括レビューを読みたい
- `docs/review/CODE_REVIEW_2026_02_16_COMPLETENESS_JP.md`（完成度パーセンテージ評価）
- `docs/review/CODE_REVIEW_2026_02_11.md`
- `docs/review/CODE_REVIEW_2026_02_10.md`

### B. 旧レビューの網羅版を遡りたい
- `docs/review/CODE_REVIEW_FULL.md`
- `docs/review/CODE_REVIEW_FULL_2026_02_08.md`
- `docs/review/CODE_REVIEW_2025.md`

### C. レポート形式で確認したい
- `docs/review/CODE_REVIEW_REPORT.md`
- `docs/notes/CODE_REVIEW_REPORT_20260204.md`
- `docs/notes/code_review_20260205.md`

### D. 原則ベースで確認したい
- `docs/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md`

---

## 3. 命名ルール（今後）

今後レビュー文書を追加する場合は、次の形式を推奨します。

- 日次/都度レビュー: `docs/review/CODE_REVIEW_YYYY_MM_DD.md`
- 実行確認付きレビュー: `docs/review/CODE_REVIEW_YYYY_MM_DD_RUNTIME_CHECK.md`
- 進捗管理（単一運用）: `docs/review/CODE_REVIEW_STATUS.md`（固定名）

これにより、同種文書の探索コストを下げ、重複管理を避けます。

---

## 4. 運用ルール（軽量）

- 新しいレビューを追加したら、このマップに 1 行追記する。
- 既存内容の上書きではなく、日時付き文書で履歴を残す。
- Issue/PR から参照する際は、まず `docs/review/CODE_REVIEW_STATUS.md` をリンクする。

---

## 5. セキュリティ観点の注意

レビュー文書には、脆弱性情報や運用上の弱点が記載される場合があります。
公開リポジトリで扱うため、以下を徹底してください。

- 実鍵・トークン・内部 URL・個人情報は記載しない。
- PoC 手順は悪用可能性を下げる粒度で記述する。
- 未修正の高リスク項目は、対応期限と暫定緩和策を併記する。
