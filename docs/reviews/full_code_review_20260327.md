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

---

## 改善実施記録（2026-03-27 追記）

### 実施内容
1. **CI での MemoryOS allowlist 検査を本番プロファイル固定で実行**
   - `.github/workflows/main.yml` の `Memory directory allowlist check` ステップに、以下を追加:
     - `VERITAS_ENV=production`
     - `VERITAS_MEMORY_DIR=/tmp/veritas_memory_ci/runtime`
     - `VERITAS_MEMORY_DIR_ALLOWLIST=/tmp/veritas_memory_ci`
     - `VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION=1`
   - これにより、CI 上で「non-production / 未設定のためスキップ」が発生しない運用へ改善。

2. **allowlist チェックスクリプトに strict mode を追加**
   - `scripts/security/check_memory_dir_allowlist.py` に
     `VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION` を導入。
   - strict mode 有効時は、production 検証がスキップされる構成（`VERITAS_ENV` 非 production または `VERITAS_MEMORY_DIR` 未設定）を **明示的に失敗** させる。
   - セキュリティ意図:
     - チェックの「未実行」を見逃してリリースするリスクを低減。
     - MemoryOS 設定ドリフトを CI で早期検知。

3. **回帰テストを追加**
   - `veritas_os/tests/test_check_memory_dir_allowlist.py` に以下を追加:
     - strict mode で検証スキップ時に失敗すること
     - strict mode で正しい production 設定時に成功すること

4. **CI 環境で strict mode をデフォルト有効化（ドリフト耐性の強化）**
   - `scripts/security/check_memory_dir_allowlist.py` の strict 判定を拡張し、
     `VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION` が未設定でも
     `CI=true` の場合は strict mode を有効化するよう改善。
   - 効果:
     - workflow 変更時に strict 用 env の付与漏れがあっても、CI 実行自体で
       「production 検証スキップ」を失敗として検知できる。
     - 既存の明示フラグ (`VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION=1`) は
       従来どおり優先され、互換性を維持。

5. **CI strict 既定化の回帰テストを追加**
   - `veritas_os/tests/test_check_memory_dir_allowlist.py` に
     `CI=true` かつ production 設定未指定時は `checker.main([])` が失敗するテストを追加。
   - これにより、将来 strict 判定ロジックが緩んだ場合の退行を自動検知可能。

### セキュリティ警告（継続）
- strict mode は `CI=true` でも既定有効になったが、ローカル/手動実行では
  既定で有効化されない。必要なジョブでは引き続き
  `VERITAS_MEMORY_DIR_CHECK_REQUIRE_PRODUCTION=1` を明示し、実行条件の意図を固定すること。
- 実運用では、`VERITAS_MEMORY_DIR_ALLOWLIST` を最小権限のディレクトリ範囲に限定し、過剰に広い許可（例: `/tmp` 全体）を避けること。
