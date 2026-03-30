---
title: Review Docs Hub (active)
doc_type: review_index
updated_at: 2026-03-30
---

# Review Docs Hub (active)

このディレクトリは、**運用中（active）** のレビュー文書を管理するハブです。

## 使い分け

- `docs/review/`
  - 日次レビュー、ステータス、運用ガイドなどの **アクティブ文書**。
- `docs/reviews/`
  - 監査・再評価・技術レビューなど、日付付きの **評価レポート群**。
- `docs/notes/`
  - 補助メモ、履歴、要約などの **補助文書**。

## まず最初に確認するファイル

1. `CODEX_START_HERE.md`
2. `CODE_REVIEW_STATUS.md`
3. `CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md`

## 命名ルール（本ディレクトリ）

- 日次レビュー: `CODE_REVIEW_YYYY_MM_DD*.md`
- 固定運用文書: `CODE_REVIEW_STATUS.md` / `CODEX_START_HERE.md`
- サマリ: `*_SUMMARY*.md`

## セキュリティ注意

- 未修正脆弱性の具体的な攻撃手順は記載しない。
- 秘密情報（鍵、トークン、内部 URL）を記載しない。
- 高リスク項目は「影響」「暫定対処」「恒久対処」をセットで記載する。
