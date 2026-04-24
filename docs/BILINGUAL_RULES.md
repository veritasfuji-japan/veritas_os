# Bilingual Documentation Maintenance Rules

# バイリンガルドキュメント運用ルール

## 1. Core policy / 基本方針
- English canonical documents remain authoritative for strict specification.
- Japanese public readers must be able to understand core product concepts from Japanese-first routes.
- Implemented fact, beta limitation, and roadmap direction must stay synchronized between EN and JA public docs.

## 2. Japanese-first public surface
以下は日本語ファースト導線として継続保守します。

- `README_JP.md`
- `docs/ja/README.md`
- `docs/INDEX.md` の日本語列
- `docs/DOCUMENTATION_MAP.md`
- 高優先度の `docs/ja/*` 解説ページ（architecture / validation / operations / governance / guides / positioning）

公開導線では、日本語読者に core public concepts を英語先行で強制しないことを原則とします。

## 3. Classification

### Type A: EN/JA fully paired
公開入口や高頻度導線。英日双方で更新する。

### Type B: JA explanation / EN canonical
英語正本を維持し、日本語では要点解説と導線を提供する。

### Type C: JA primary
日本語コミュニティ向けレビュー・監査文書等。必要時に EN 要約を追加。

## 4. Link policy
1. `README.md` は EN canonical を優先してリンクする。
2. `README_JP.md` は **core public concepts で docs/ja を先にリンク**する。
3. JAページに対応がない場合のみ、`英語正本` と明示して EN にリンクする。
4. 各 JA 解説ページは `## 英語正本` セクションを持つ。

## 5. Full translation policy
- 深い技術文書を毎回完全翻訳する必要はありません。
- 日本語解説ページ（要点 + 実装確認 + 制限 + 英語正本リンク）を許容します。
- ただし public-facing の理解入口では EN 強制導線を避けます。
- 実装済み事実・ベータ制限・本番要件・将来ロードマップは、同一段落で混在させず明確に分離します。

## 6. Drift control
- `scripts/quality/check_bilingual_docs.py` で公開導線とリンク整合を検査する。
- `README.md` と `README_JP.md` の bind-governed effect path は同期維持する。
- `docs/INDEX.md` と `docs/DOCUMENTATION_MAP.md` のローカルパスは存在チェックを通す。

## 7. Review checklist (PR)
- README_JP の事実記述が README と一致しているか。
- 追加した高優先度 EN 文書に JA 解説ページを作成したか。
- JA ページに過大主張（認証済み・規制承認済み・本番保証）が含まれていないか。
- ドキュメント品質チェック（`make check-bilingual-docs`）が通るか。
