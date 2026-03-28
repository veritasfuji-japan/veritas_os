# Runtime Data Policy

## 目的

このドキュメントは、`fresh clone` 直後にリポジトリが **実行履歴ゼロ** の状態であることを保証するための運用ルールを定義します。

## Fresh clone の期待状態

- `chosen_title` / decision history / trust log / world state の実データはコミットされない。
- runtime 出力は Git 追跡対象外で、初期状態は空ディレクトリ（`.gitkeep` のみ）。
- sample data が必要な場合は `veritas_os/sample_data/` のような専用パスに隔離する。

## Git に含めないもの（runtime data）

- `runtime/**` 配下の実行データ
- `logs/**`, `scripts/logs/**`
- `datasets/generated/**`
- `data/runtime/**`
- `storage/**`, `cache/**`
- `*.jsonl`, `*.db`, `*.sqlite`, `*.log`, `*.tmp`

## 保存先分離ポリシー

- 開発: `runtime/dev/`
- テスト: `runtime/test/`（可能ならテストごとに `tmp_path`）
- デモ: `runtime/demo/`
- 本番: `runtime/prod/` または明示的に設定した外部パス

`VERITAS_RUNTIME_NAMESPACE` を使って保存先を切り替え可能。

## Cleanup 手順

```bash
python scripts/reset_repo_runtime.py --dry-run
python scripts/reset_repo_runtime.py --apply
```

- `--dry-run`: 削除対象を表示のみ
- `--apply`: 実際に削除し、`runtime/{dev,test,demo,prod}/.gitkeep` を維持

## 実装ルール

- 初回起動時に seed の decision 履歴を注入しない。
- fallback で `chosen_title` に擬似値を自動保存しない。
- `world_state.meta.repo_fingerprint` が現在リポジトリと不一致の場合は、
  cross-clone 汚染防止のため fresh state に自動リセットする。
- `decide_*.json` に保存する `context.world_state` は current user の最小スナップショットに圧縮する。
- テストは runtime 実パスではなく一時ディレクトリを優先する。
- 監査ログ機構（TrustLog）は維持しつつ、データファイル自体はコミットしない。
