# 外部監査準備性（External Audit Readiness）

## 位置づけ
外部監査人・DD担当・内部統制担当が、VERITAS の監査提出準備を確認するための日本語解説です。

## 要点
- 監査では Decision Governance、bind境界、TrustLog の連結証跡を確認します。
- 主要証跡は `governance_identity`、`bind_summary`、`BindReceipt`、Replay 出力です。
- Mission Control と API の両経路で同一証跡を参照できることが重要です。

## VERITASにおける意味
- operator-facing governance surface を監査説明可能な形で提示するための基礎文書です。
- fail-closed 運用や bind判定理由を、監査時に再現可能な情報へ落とし込みます。

## 実装上の確認ポイント
- bind-receipts list/export/detail が取得できるか。
- エビデンスバンドルの作成手順と保管責任分界が明確か。
- 監査時に参照する API・ログ・Runbook を環境ごとに固定しているか。

## 現時点の制限
- 外部監査実施済み・認証取得済みを意味する文書ではありません。
- 本番導入前に証跡保存方針、アクセス統制、鍵管理設計を確定してください。

## 英語正本
- [docs/en/validation/external-audit-readiness.md](../../en/validation/external-audit-readiness.md)
