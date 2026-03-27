# 全コードレビュー報告書（2026-03-27）

## 対象範囲
- リポジトリ全体を対象に、アーキテクチャ責務境界・セキュリティ姿勢・静的品質・回帰健全性を確認。
- 自動検査スクリプト、lint、重点テストを組み合わせて評価。

## 実行コマンド
1. `python scripts/architecture/check_responsibility_boundaries.py`
2. `python scripts/architecture/check_core_complexity_budget.py`
3. `python scripts/security/check_subprocess_shell_usage.py`
4. `python scripts/security/check_httpx_raw_upload_usage.py`
5. `python scripts/security/check_memory_dir_allowlist.py`
6. `python scripts/security/check_runtime_pickle_artifacts.py`
7. `python scripts/security/check_next_public_key_exposure.py`
8. `ruff check veritas_os scripts chainlit_app.py`
9. `pytest -q veritas_os/tests/test_responsibility_boundaries.py veritas_os/tests/test_security_review_fixes.py veritas_os/tests/test_check_subprocess_shell_usage.py`
10. `rg -n "\\beval\\(|\\bexec\\(|pickle\\.loads|yaml\\.load\\(|subprocess\\.(Popen|run|call)\\(.*shell\\s*=\\s*True" veritas_os scripts`

## 結果サマリ
- **責務境界チェック**: 合格。
- **Planner / Kernel 複雑度予算**: 合格。
- **セキュリティスキャナ（subprocess/httpx/pickle/NEXT_PUBLIC 露出）**: 合格。
- **MemoryOS allowlist チェック**: 本実行環境では `VERITAS_MEMORY_DIR` 未設定のためスキップ。
- **Python lint（ruff）**: 合格。
- **重点セキュリティ/境界テスト**: 24件合格。
- **危険APIパターン検索（rg）**: 実装コードにヒットなし（テスト用の意図的サンプルのみヒット）。

## 詳細所見
### 1) 責務分離（Planner / Kernel / FUJI / MemoryOS）
- アーキテクチャ検査にて、責務境界違反は検出されなかった。
- `planner.py` および `kernel.py` は定義済み複雑度上限を超過していない。
- 現状構成は、責務の越境を防ぐプロジェクト方針と整合している。

### 2) セキュリティ姿勢
- 本番コードで `subprocess(..., shell=True)` 相当の危険利用は検出されなかった。
- `httpx` の非推奨な raw upload パターンは検出されなかった。
- 旧来の runtime pickle artifact は検出されなかった。
- フロントエンド環境変数において、禁止対象の `NEXT_PUBLIC_*` 秘密情報類推名は検出されなかった。

### 3) 残留リスク警告（重要）
1. **MemoryOS のパス制御が本実行では完全検証できていない**
   - `check_memory_dir_allowlist.py` は non-production / `VERITAS_MEMORY_DIR` 未設定のためスキップ。
   - リスク: 本番環境の設定不備時に、期待される運用制約（許可ディレクトリ制御）が十分に機能しない可能性。
   - 推奨: `VERITAS_ENV=production` と明示的な `VERITAS_MEMORY_DIR` を設定した staging/CI で同検査を必須実行。

2. **レビュー信頼性は自動検査主導**
   - 本レビューは高い網羅性を持つが、全ファイル逐行の手作業監査を単回で完了したものではない。
   - 推奨: 高リスク領域（`api/server.py`、`core/pipeline.py`、`core/fuji.py`、永続化境界）を継続的に深掘り監査。

## 推奨アクション
1. production プロファイルで allowlist 検査がスキップされた場合に CI を fail させる。
2. FUJI gate のバイパス境界条件、replay 差分整合性のテストをさらに拡張する。
3. すべての PR でアーキテクチャ検査を継続し、責務ドリフトを予防する。

## 結論
- 本実行で確認した範囲では、アーキテクチャ統制と基礎セキュリティ統制は良好であり、即時の重大ブロッカーは検出されなかった。
- ただし、**MemoryOS allowlist の本番相当検証がスキップされた点は明確な警告事項**であり、環境を揃えた再検証が必要。
