# 精密レビュー（2026-04-20）

## 対象
- リポジトリ全体（特に認証・CORS・フロントエンドBFF境界・危険プリセット）
- 実行ベースの静的チェック + セキュリティ関連テスト

## 実施コマンド
1. `python scripts/architecture/check_responsibility_boundaries.py`
2. `python scripts/security/check_subprocess_shell_usage.py`
3. `python scripts/security/check_unsafe_dynamic_execution_usage.py`
4. `python scripts/security/check_httpx_raw_upload_usage.py`
5. `python scripts/security/check_next_public_key_exposure.py`
6. `python scripts/security/check_memory_dir_allowlist.py`
7. `pytest -q veritas_os/tests/test_production_trustlog.py veritas_os/tests/test_production_governance.py veritas_os/tests/test_backend_improvements.py -k "api_key or cors or trustlog"`

## 総評
- **責務境界（Planner / Kernel / FUJI / MemoryOS）**: 自動検証は通過。
- **明確な即時脆弱性（Critical/High）**: 今回のレビュー範囲では未検出。
- **運用上のセキュリティ注意点**: 2件（いずれも既存実装の設計上トレードオフ）。

## 指摘事項

### 1) SSE / WebSocket の query API key 互換モード
- **重要度**: 中（運用設定依存）
- **内容**: `X-API-Key` ヘッダが無い場合、特定フラグで query パラメータ認証を許可する互換経路が存在する。
- **リスク**: URL経由資格情報は、アクセスログ/リファラ/監視基盤で漏えいしやすい。
- **現状の防御**:
  - 本番判定時はフラグが要求されても拒否（fail-closed）
  - 明示的な warning ログを出力
- **推奨**:
  - 非本番でも移行期間外は `VERITAS_ALLOW_SSE_QUERY_API_KEY` / `VERITAS_ALLOW_WS_QUERY_API_KEY` を無効化
  - CI/CD で該当フラグの常時監査を追加

### 2) フロントエンド危険プリセットの有効化フラグ
- **重要度**: 低〜中（環境管理依存）
- **内容**: 開発環境で `NEXT_PUBLIC_ENABLE_DANGER_PRESETS=true` を設定すると危険プロンプト例を表示可能。
- **リスク**: 検証環境/共有環境で誤有効化すると、誤操作や監査負荷増大につながる。
- **現状の防御**:
  - `NODE_ENV=production` では無効化
- **推奨**:
  - ステージング含む非本番でのデフォルトOFF徹底
  - 運用Runbookに「危険プリセット有効化禁止（限定検証時のみ）」を明記

## ポジティブ所見
- BFF設定で `NEXT_PUBLIC_VERITAS_API_BASE_URL` を本番でブロックし、サーバー側URLのみ許可する設計は妥当。
- CORSは wildcard + credentials を防止する実装で、典型的な誤設定事故を抑止している。
- TrustLog/ガバナンス周辺の対象テストは今回実行範囲で全件成功。

## 追加提案（任意）
- セキュリティフラグ（query認証移行フラグ、danger presetフラグ）の**起動時サマリー出力**を1箇所へ集約し、SREの可観測性を向上。
- `scripts/production_validation.sh` に「query API key フラグ=OFF」を検証する明示チェックを追加。

