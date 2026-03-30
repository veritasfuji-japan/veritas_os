---
title: Reviews Archive Guide
doc_type: review_archive_index
updated_at: 2026-03-30
---

# Reviews Archive Guide

このディレクトリは、日付付きレビュー・再評価のアーカイブです。

## 推奨ファイル命名

- `*_YYYYMMDD.md` 形式を推奨。
- 言語サフィックスが必要な場合は `*_ja_YYYYMMDD.md` のように統一。
- 大文字/小文字・区切り（`-` と `_`）は新規作成時に混在させない。

## 参照優先度

- 最新の総合レビュー:
  - `full_code_review_20260327.md`
  - `system_improvement_review_ja_20260327.md`
- セキュリティ観点レビュー:
  - `THREAT_MODEL_STRIDE_LINDDUN_20260314.md`
- 再評価・差分確認:
  - `CODE_REVIEW_REASSESSMENT_2026_03_23_JP.md`
  - `precision_code_review_ja_20260319_reassessment.md`

## 運用ルール

- 既存レポートは原則 immutable（追記のみ）。
- 正誤修正は、元文書を上書きせず「reassessment」文書で記録。
- 横断ステータス更新は `docs/review/CODE_REVIEW_STATUS.md` を正とする。
