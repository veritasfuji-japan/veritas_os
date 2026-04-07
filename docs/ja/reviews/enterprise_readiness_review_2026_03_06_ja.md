# Enterprise Readiness Review (2026-03-06)

## 対象・レビュー方針
- 対象: `veritas_os/`（Pythonバックエンド）, `frontend/`（Next.js）, `packages/`（共通TSパッケージ）, `scripts/`。
- 方針: 全ファイルを人手で逐語確認するのではなく、**全コードベースを対象に自動テスト + 静的観点スキャン + アーキテクチャ境界検証**を実施し、エンタープライズ適合性を評価。

## 実施コマンド（要約）
1. `pytest -q`
   - 結果: `2750 passed, 3 skipped, 5 warnings`
2. `python scripts/architecture/check_responsibility_boundaries.py`
   - 結果: `Responsibility boundary check passed.`
3. `python scripts/security/check_next_public_key_exposure.py`
   - 結果: `No disallowed NEXT_PUBLIC secret-like variable names found.`
4. `rg -n "shell=True|subprocess\.|os\.system\(|yaml\.load\(|pickle\.loads|jwt\.decode\(.*verify=False|md5\(" veritas_os scripts frontend packages`
   - 結果: 危険パターン候補を横断抽出（`shell=True` 直使用は未検出）。
5. `rg -n "(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}|ghp_[0-9A-Za-z]{36}|sk-[A-Za-z0-9]{20,})" .`
   - 結果: 検出なし。

## 総合評価（Enterprise readiness）
- **評価: 条件付きで「エンタープライズ運用可能（B+）」**
- 理由:
  - テスト密度が非常に高く、回帰耐性は高水準。
  - Planner / Kernel / Fuji / MemoryOS の責務境界を静的チェックで継続監視できる。
  - APIキー、署名、PIIマスク、Trust Log など監査運用向けの設計が存在。
- ただし、以下の重要ギャップを解消すると「A帯（監査厳格環境）」に到達しやすい。

## 強み（エンタープライズ観点）
1. **責務境界の自動検査**
   - `scripts/architecture/check_responsibility_boundaries.py` にて、core間の禁止依存をASTで検出。
2. **フロントエンド秘密情報露出の予防策**
   - `scripts/security/check_next_public_key_exposure.py` が `NEXT_PUBLIC_...KEY/TOKEN/SECRET/PASSWORD` を禁止。
3. **運用セキュリティ配慮（Kernel）**
   - `veritas_os/core/kernel.py` で subprocess 実行時の confinement 条件や実行バイナリ検証、ログFDの安全オープンを実装。
4. **APIの認証基盤**
   - `openapi.yaml` で `X-API-Key` を定義し、`veritas_os/api/server.py` の多数エンドポイントで依存注入による認証を強制。

## 主要リスクと警告（必読）

### ⚠️ リスク1: フロントBFF経由APIにユーザー認証レイヤが見えない
- `frontend/app/api/veritas/[...path]/route.ts` はサーバ側APIキーで上流APIを代理呼び出しするが、
  ルート自体のユーザー認証（例: セッション/JWT/SSO）や権限判定がコード上で確認できない。
- 影響:
  - 公開環境でルーティング設定を誤ると、内部APIキー権限を実質的に匿名利用される可能性。
- 推奨:
  - BFFルートに `authn/authz` を必須化。
  - 最低でもIP制限・CSRF対策・レート制限・監査ログを追加。

### ⚠️ リスク2: 依存関係の脆弱性管理プロセスがコード上で明示されない
- `pyproject.toml` はバージョン固定を実施しているが、
  `pip-audit` / `npm audit` / `osv-scanner` 等の定期実行・CIゲート化がレビュー対象内で明示されない。
- 影響:
  - 新規CVE混入時の検知遅延。
- 推奨:
  - CIでSCA（Software Composition Analysis）を必須ジョブ化。

### ⚠️ リスク3: テスト警告の恒常化
- `pytest` 実行時に外部ライブラリ由来の警告が5件継続。
- 影響:
  - 重大警告の埋没。
- 推奨:
  - 警告管理ポリシー（allowlistと期限）を定義し、期限切れでfail化。

## 追加改善提案（優先度順）
1. **P0**: `frontend/app/api/veritas/[...path]/route.ts` に強制認証と権限マトリクスを導入。
2. **P0**: CIに `pip-audit` / `npm audit --production` を追加し、重大CVSSでデプロイブロック。
3. **P1（対応済み）**: 監査向けにSLO/SLI（API latency, error budget）と運用Runbookを `docs/ja/operations/enterprise_slo_sli_runbook_ja.md` に明文化。
4. **P1（対応済み）**: BFFとAPI双方で相関ID（`X-Trace-Id` / `X-Request-Id`）を必須伝播し、監査容易性を向上。
5. **P2（対応済み）**: `scripts/quality/check_warning_allowlist.py` と `config/test_warning_allowlist.json` を追加し、`pytest` の ignore 警告を期限付きallowlistで管理（期限切れ・メタデータ欠落でfail）。

## 結論
- 現状は、**テスト網羅・責務境界・基本セキュリティ機構**の観点で高水準。
- 一方で、エンタープライズ本番（特に厳格監査環境）としては、
  **BFFユーザー認証の明示化**と**依存脆弱性スキャンのCI強制**が必須。
- これら2点を満たせば、実運用レベルの信頼性はさらに高まる。
