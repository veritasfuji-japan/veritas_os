# CODEX START HERE（レビュー着手 5 分ガイド）

目的: `docs/review/` と `docs/notes/` の探索コストを下げ、**新規担当者が 5 分以内にレビュー開始**できる状態を作る。

---

## 1) 参照優先順（迷ったらこの順）

1. `docs/review/CODE_REVIEW_STATUS.md`
   - 最新の修正進捗（Fix / Deferred / Accepted）を確認
2. `docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md`
   - 実行確認済み・未実施項目（環境制約）を確認
3. `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`
   - 目的別の参照先を選定（包括レビュー、原則、過去履歴）
4. 目的に応じて追加参照
   - 原則確認: `docs/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md`
   - 責務境界確認: `docs/review/SCHEMA_REVIEW_2026_02_23.md`

> 上記 1〜3 を読めば、以降どの文書を読むべきかを判断できる。

---

## 2) 必須コマンド（開始 2 分）

```bash
# 1. レビュー関連文書の入口確認
rg --files docs/review docs/notes | head -n 50

# 2. 最新ステータス確認
sed -n '1,200p' docs/review/CODE_REVIEW_STATUS.md

# 3. 実行確認の最新結果確認
sed -n '1,220p' docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md

# 4. 文書マップ確認（参照先決定）
sed -n '1,220p' docs/notes/CODE_REVIEW_DOCUMENT_MAP.md
```

---

## 3) 禁止事項（責務境界）

以下の越境は **禁止**（レビュー・修正提案時の前提）:

- Planner / Kernel / Fuji / MemoryOS の責務をまたぐ再設計
- API 境界の外側での暫定パッチ（層を飛び越えた修正）
- レビュー PR での大規模なアーキテクチャ変更

実施してよいこと（境界内）:

- ドキュメント整理、命名・参照導線の改善
- schema / API 境界内で完結する入力検証の改善
- テスト・CI・運用手順の明確化

---

## 4) PR テンプレート（レビュー文書更新用）

```md
## Summary
- 何を追加/更新したか（3行以内）
- なぜ必要か（探索コスト or 品質観点）

## Scope
- 変更ファイル:
  - docs/review/...
  - docs/notes/...
- 非変更（明示）:
  - Planner / Kernel / Fuji / MemoryOS の実装

## Checks
- [ ] 参照優先順が 1 ページで追える
- [ ] 必須コマンドが再実行可能
- [ ] 禁止事項（責務境界）が明記されている

## Security
- [ ] 秘匿情報（鍵・トークン・内部URL・個人情報）を記載していない
- [ ] 脆弱性情報は悪用可能性を下げた粒度で記載した

## Done Criteria
- [ ] 新規担当者が 5 分以内にレビュー開始できる
```

---

## 5) Done 条件（受け入れ基準）

- 新規担当者が本ページのみで開始手順を理解できる
- 必須コマンド実行後、次に読む文書を即決できる
- 責務境界（Planner / Kernel / Fuji / MemoryOS）を越えない運用が明記されている
