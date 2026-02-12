# コードレビュー 2026-02-12（Agent）

## 対象範囲
- `veritas_os` / `frontend` / `packages` を対象にしたリポジトリ全体のライトレビュー（ベンダリング済み `node_modules` は除外）。
- 静的な grep ベースのセキュリティスキャン + Python lint + Python テスト実行。

## 実行コマンド
1. `rg --files | head -n 200`
2. `rg -n "(eval\(|exec\(|subprocess\.|pickle\.loads|yaml\.load\(|os\.system\(|requests\.(get|post)\(|http://)" veritas_os frontend packages --glob '!**/node_modules/**'`
3. `python -m pytest -q -x`
4. `ruff check veritas_os`

## 指摘事項サマリ

### 1) テスト環境の不整合（High）
- `python -m pytest -q -x` は以下で失敗:
  - `async def functions are not natively supported`
  - `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`
- 影響:
  - デフォルト環境で async 統合テストを実行できず、CI の信頼性が低下する。
  - async 経路の回帰を見逃す可能性がある。
- 推奨対応:
  - テスト依存関係に `pytest-asyncio` を追加してバージョン固定（または `pytest-anyio` へ統一）。
  - `pyproject.toml` に pytest のマーカー設定を明示する。

### 2) 通信デフォルトが HTTP である箇所が複数存在（Medium）
- 実行時デフォルトとして `http://localhost` / `http://127.0.0.1` を利用している箇所が複数ある。
- 影響:
  - ローカル開発用途としては妥当だが、共有環境・ステージング・本番へ設定が流用されるとリスクになる。
- 推奨対応:
  - 本番向けに `https://` を推奨する設定方針と許可ホスト制御（allowlist）を明文化する。
  - 非 loopback 宛ての HTTP が設定された場合に起動時警告を出す。

### 3) 外部通信面は存在するが、再試行/エラー制御は概ね良好（Info）
- `veritas_os/tools/web_search.py` と `veritas_os/tools/github_adapter.py` には、再試行と上限付きバックオフの実装がある。
- 良い点:
  - タイムアウト指定と再試行上限がある。
  - `github_adapter` にはエラーメッセージのサニタイズがある。
- 推奨対応:
  - 本番ハードニングとして、任意で外向き通信先ドメインの allowlist 強制を検討する。

## 総評
- lint 結果と広範囲テスト実行の進捗から、コードベース全体の健全性は概ね良好。
- 最優先の改善点は、async テスト実行基盤（plugin / marker）整合の確保。
