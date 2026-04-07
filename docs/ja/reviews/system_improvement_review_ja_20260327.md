# VERITAS システム改善レビュー（2026-03-27）

## 実施サマリー
- 対象: `veritas_os/api/startup_health.py` と関連テスト
- 目的: 共有ステージング環境での auth fail-open 誤設定を、警告止まりではなく fail-closed で遮断
- 境界確認: Planner / Kernel / FUJI / MemoryOS の責務には未介入（API 起動時の設定検証のみ変更）

## 改善内容
1. `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` または `VERITAS_AUTH_STORE_FAILURE_MODE=open` が指定された場合:
   - `VERITAS_ENV=prod|production` は従来通り起動拒否
   - **`VERITAS_ENV=stg|staging` も新たに起動拒否**
2. docstring のセキュリティ方針を更新し、staging を「保護対象の pre-production」と明示
3. 回帰防止テストを追加
   - `staging` + `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` で `RuntimeError`
   - `stg` + `VERITAS_AUTH_STORE_FAILURE_MODE=open` で `RuntimeError`

## セキュリティ警告（運用者向け）
- **[HIGH] 認証ストア fail-open は、nonce / rate-limit / auth failure 制御を弱めます。**
- 本変更後、staging でも fail-open は許可されません。IaC/環境変数配布の段階で該当フラグを除外してください。

## 期待効果
- 共有検証環境で「本番に近いセキュリティ前提」を維持
- 設定ドリフト時に警告見落としで進行するリスクを削減
- fail-closed 運用姿勢の一貫性向上
