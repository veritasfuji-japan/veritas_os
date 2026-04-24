# Bind-Boundary Governance Artifacts（日本語解説）

## 位置づけ
この文書は bind 境界で生成・保存されるガバナンス成果物の読み方を整理する日本語解説です。監査提出、運用審査、障害調査の担当者向けです。

## 要点
- bind 境界では `decision -> execution_intent -> BindReceipt` の成果物系譜を保持します。
- `bind_summary` / bind概要 は運用表示向け、`BindReceipt` / bind証跡 は監査向けの完全証跡です。
- 署名・ハッシュ連鎖・target metadata を使い、後追い検証可能な状態を維持します。

## VERITASにおける意味
- Decision Governance の承認結果が、bind 境界で実際にどう適用されたかを示す中核資料です。
- TrustLog と Mission Control をまたいで、operator-facing governance surface の共通証跡になります。
- fail-closed / 安全側停止 が発生した場合も、`BindReceipt` で理由を追跡できます。

## 実装上の確認ポイント
- `/v1/governance/bind-receipts` と `/v1/governance/bind-receipts/{bind_receipt_id}` の出力を確認する。
- mutation/export 応答で `bind_summary` が返ることを確認する。
- ガバナンス成果物署名運用（鍵 ID・検証時刻・検証結果）を Runbook で確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 監査適合性は環境依存です。第三者認証や規制承認を本書だけで主張しません。
- 本番導入前に統合試験、鍵管理、証跡保全設計が必要です。

## 英語正本
- [docs/en/architecture/bind-boundary-governance-artifacts.md](../../en/architecture/bind-boundary-governance-artifacts.md)
