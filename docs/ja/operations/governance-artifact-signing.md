# ガバナンス成果物署名（日本語解説）

## 位置づけ
ガバナンス成果物の署名・検証運用を日本語で把握するための文書です。

## 要点
- policy bundle と関連成果物の署名検証は改ざん耐性の基礎です。
- `governance_identity` と署名検証結果を監査時に関連付けます。
- secure/prod では未署名・不正署名を fail-closed で拒否します。

## VERITASにおける意味
- Bind-Boundary の admissibility と成果物真正性を結びつける中核運用です。
- TrustLog のチェーンと組み合わせ、監査時の説明責任を支えます。

## 実装上の確認ポイント
- 署名鍵ID、検証時刻、検証結果を証跡として保持する。
- ポリシーバンドル昇格手順と署名検証手順を一体で運用する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 鍵管理は環境依存です。運用責任分界の設計が必要です。
- 本文書は認証取得を主張するものではありません。

## 英語正本
- [docs/en/operations/governance-artifact-signing.md](../../en/operations/governance-artifact-signing.md)
