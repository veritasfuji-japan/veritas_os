# UI Architecture Notes

## 目的

- frontend を App Router ベースで独立起動可能にする。
- API 型を `packages/types` に集約し、唯一の真実にする。
- テーマ・トークン・共通 UI を `packages/design-system` に集約する。

## パッケージ責務

- `frontend/`: 画面実装とユーザー操作。
- `packages/types/`: API contract の型。
- `packages/design-system/`: UI トークン、テーマ、共通コンポーネント。

## 運用メモ

- 新しい API レスポンス型は `packages/types/src/index.ts` に追加。
- 共通 UI は `packages/design-system/src` へ追加し、frontend 側で直接複製しない。
- frontend では `@veritas/types` と `@veritas/design-system` を import して利用する。
