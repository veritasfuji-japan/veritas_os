# CODE REVIEW FULL (2026-03-14, JP)

## 対象と方針
- 対象: `veritas_os/`（Pythonバックエンド中心）と静的チェック/セキュリティチェック用スクリプト。
- 方針: 既存アーキテクチャ責務（Planner / Kernel / Fuji / MemoryOS）を横断破壊しない観点で、
  境界逸脱・セキュリティ・品質ゲートの実行結果を優先して確認。

## 実行したチェック
1. `python scripts/architecture/check_responsibility_boundaries.py`
   - 結果: pass（責務境界違反なし）
2. `python scripts/security/check_httpx_raw_upload_usage.py`
   - 結果: pass（非推奨な生アップロード利用なし）
3. `python scripts/security/check_runtime_pickle_artifacts.py`
   - 結果: pass（危険なruntime pickle artifactなし）
4. `python scripts/security/check_next_public_key_exposure.py`
   - 結果: pass（公開してはいけないNEXT_PUBLIC系キー名なし）
5. `ruff check veritas_os`
   - 結果: pass（PEP8/静的Lint観点で問題なし）
6. `pytest -q veritas_os/tests/test_responsibility_boundary_checker.py veritas_os/tests/test_check_httpx_raw_upload_usage.py veritas_os/tests/test_check_runtime_pickle_artifacts.py`
   - 結果: pass（18件）

## レビュー結果サマリ
- **重大度 Critical:** 0件
- **重大度 High:** 0件
- **重大度 Medium:** 0件
- **重大度 Low:** 2件（運用上の注意）

## 指摘詳細

### Low-1: Gitメタデータ取得失敗時のバージョン情報欠落
- 観測: `replay_engine` で `git rev-parse` 実行失敗時は `"unknown"` へフォールバック。
- 影響: セキュリティ事故ではないが、監査追跡で再現性トレースが弱くなる可能性。
- 推奨: CIでコミットSHAを環境変数注入し、`unknown` の発生を監視する。

### Low-2: subprocess 利用点の継続監視
- 観測: `subprocess` 利用箇所は複数あるが、今回確認範囲では `shell=True` の危険呼び出しは未検出。
- 影響: 現時点は顕在リスク低いが、将来の改修でコマンド注入面が増える余地がある。
- 推奨: pre-commit/CI に「`shell=True` 禁止」「外部入力をコマンド配列へ直接連結禁止」の静的ルールを維持。

## セキュリティ警告（必読）
- 今回のレビュー実行範囲では**直ちに悪用可能な高危険度脆弱性は未検出**。
- ただし、`subprocess` 呼び出しは設計上の攻撃面になりやすいため、
  今後も入力正規化・固定引数化・最小権限実行の継続を強く推奨。

## 結論
- 現行コードベースは、今回実施した責務境界・セキュリティ・Lint・関連テストの観点で健全。
- 次フェーズは、運用監視（`unknown` 版情報率）と `subprocess` ガードレールの継続が妥当。
