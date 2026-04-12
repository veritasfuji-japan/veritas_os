---
title: コードレビュー文書マップ（整理版）
doc_type: review_document_index
latest: true
updated_at: 2026-03-30
---

# コードレビュー文書マップ（整理版）

最終更新: 2026-03-30

コードレビュー関連 Markdown の探索コストを下げるため、
`docs/ja/reviews` / `docs/ja/reviews` / `docs/notes` の役割を明示します。

---

## 1. ディレクトリ責務

- `docs/ja/reviews/`: 運用中（active）のレビュー文書。
- `docs/ja/reviews/`: 日付付き監査・再評価レポート（アーカイブ）。
- `docs/archive/notes/`: 補助メモ・履歴・参照マップ（アーカイブ済み）。

> 以後、レビュー着手時は `docs/ja/reviews/readme_ja.md` を起点にする。

---

## 2. まず最初に見る文書（現行の正）

1. `docs/ja/reviews/codex_start_here_ja.md`
2. `docs/ja/reviews/code_review_status_ja.md`
3. `docs/ja/reviews/code_review_2026_02_11_runtime_check_ja.md`
4. `docs/ja/reviews/readme_ja.md`

### README / Runbook の正本

- 導入判断・責務境界・beta positioning の正本: `README_JP.md`
- degraded 状態の運用意味・アラート方針・復旧手順の正本:
  `docs/ja/operations/enterprise_slo_sli_runbook_ja.md`
- `veritas_os/README_JP.md` は補助説明であり、production readiness の最終判断根拠として単独利用しない。

---

## 3. 参照目的別の読み分け

### A. 直近の包括レビューを読みたい

- `docs/ja/reviews/full_code_review_20260327_ja.md`
- `docs/ja/reviews/system_improvement_review_ja_20260327.md`
- `docs/ja/reviews/code_review_status_ja.md`

### B. セキュリティ・脅威モデル視点で確認したい

- `docs/ja/reviews/threat_model_stride_linddun_20260314_ja.md`
- `docs/ja/reviews/security_audit_2026_03_12_ja.md`

### C. 旧レビューの履歴を遡りたい

- `docs/ja/reviews/code_review_full_ja.md`
- `docs/ja/reviews/code_review_full_2026_02_08_ja.md`
- `docs/en/reviews/code_review_2025.md`

---

## 4. 命名ルール（今後）

- 運用中レビュー（`docs/ja/reviews`）:
  - `CODE_REVIEW_YYYY_MM_DD*.md`
  - 固定名: `code_review_status_ja.md`
- アーカイブ（`docs/ja/reviews`）:
  - `*_YYYYMMDD.md`
  - 日本語版は必要に応じて `*_ja_YYYYMMDD.md`

---

## 5. 運用ルール（軽量）

- 新しいレビューを追加したら、このマップか `docs/ja/reviews/readme_ja.md` に追記。
- 履歴文書は原則 immutable（修正時は reassessment 文書を追加）。
- Issue/PR から参照する際は、まず `docs/ja/reviews/code_review_status_ja.md` をリンク。

---

## 6. セキュリティ観点の注意

- 実鍵・トークン・内部 URL・個人情報は記載しない。
- PoC 手順は悪用可能性を下げる粒度で記述する。
- 未修正の高リスク項目は、対応期限と暫定緩和策を併記する。
