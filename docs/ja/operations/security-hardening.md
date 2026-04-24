# セキュリティハードニング（日本語解説）

## 位置づけ
VERITAS の secure/prod 運用に向けたハードニング観点を日本語で把握するための文書です。

## 要点
- fail-closed を前提に、秘密情報管理・署名検証・監査ログ保全を強化します。
- posture 設定（dev/staging/secure/prod）で安全既定値を明示的に分離します。
- 運用変更は監査可能な手順と証跡を伴う必要があります。

## VERITASにおける意味
- Decision Governance の有効性は、ハードニングされた運用環境で初めて成立します。
- FUJI Gate・TrustLog・governance artifact signing を横断した統制が必要です。

## 実装上の確認ポイント
- posture関連環境変数と override 利用条件を確認する。
- 外部シークレットマネージャー、署名鍵、監査ログ保全設定を確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 本文書はチェックリストであり、第三者セキュリティ認証ではありません。
- 本番導入前に脅威モデルと運用審査を実施してください。

## 英語正本
- [docs/en/operations/security-hardening.md](../../en/operations/security-hardening.md)
