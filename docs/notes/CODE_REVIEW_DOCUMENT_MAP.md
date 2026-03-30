---
title: コードレビュー文書マップ（整理版）
doc_type: review_document_index
latest: true
updated_at: 2026-03-30
---

# コードレビュー文書マップ（整理版）

最終更新: 2026-03-30

コードレビュー関連 Markdown の探索コストを下げるため、
`docs/review` / `docs/reviews` / `docs/notes` の役割を明示します。

---

## 1. ディレクトリ責務

- `docs/review/`: 運用中（active）のレビュー文書。
- `docs/reviews/`: 日付付き監査・再評価レポート（アーカイブ）。
- `docs/notes/`: 補助メモ・履歴・参照マップ。

> 以後、レビュー着手時は `docs/review/README.md` を起点にする。

---

## 2. まず最初に見る文書（現行の正）

1. `docs/review/CODEX_START_HERE.md`
2. `docs/review/CODE_REVIEW_STATUS.md`
3. `docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md`
4. `docs/review/README.md`

### README / Runbook の正本

- 導入判断・責務境界・beta positioning の正本: `README_JP.md`
- degraded 状態の運用意味・アラート方針・復旧手順の正本:
  `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md`

---

## 3. 参照目的別の読み分け

### A. 直近の包括レビューを読みたい

- `docs/reviews/full_code_review_20260327.md`
- `docs/reviews/system_improvement_review_ja_20260327.md`
- `docs/review/CODE_REVIEW_STATUS.md`

### B. セキュリティ・脅威モデル視点で確認したい

- `docs/reviews/THREAT_MODEL_STRIDE_LINDDUN_20260314.md`
- `docs/review/SECURITY_AUDIT_2026_03_12.md`

### C. 旧レビューの履歴を遡りたい

- `docs/review/CODE_REVIEW_FULL.md`
- `docs/review/CODE_REVIEW_FULL_2026_02_08.md`
- `docs/review/CODE_REVIEW_2025.md`

---

## 4. 命名ルール（今後）

- 運用中レビュー（`docs/review`）:
  - `CODE_REVIEW_YYYY_MM_DD*.md`
  - 固定名: `CODE_REVIEW_STATUS.md`
- アーカイブ（`docs/reviews`）:
  - `*_YYYYMMDD.md`
  - 日本語版は必要に応じて `*_ja_YYYYMMDD.md`

---

## 5. 運用ルール（軽量）

- 新しいレビューを追加したら、このマップか `docs/review/README.md` に追記。
- 履歴文書は原則 immutable（修正時は reassessment 文書を追加）。
- Issue/PR から参照する際は、まず `docs/review/CODE_REVIEW_STATUS.md` をリンク。

---

## 6. セキュリティ観点の注意

- 実鍵・トークン・内部 URL・個人情報は記載しない。
- PoC 手順は悪用可能性を下げる粒度で記述する。
- 未修正の高リスク項目は、対応期限と暫定緩和策を併記する。
