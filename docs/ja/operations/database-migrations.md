# データベースマイグレーション（日本語解説）

## 位置づけ
DBスキーマ変更を安全に適用するための確認観点を日本語で示す解説です。

## 要点
- migration は機能追加だけでなく監査証跡の整合維持を目的とします。
- 適用・ロールバック・検証を手順化し、変更履歴を追跡可能にします。
- bind証跡や governance_identity に関わる列変更は特に慎重に扱います。

## VERITASにおける意味
- Decision Governance の再現性は、スキーマ互換性とデータ整合に依存します。
- Replay と Mission Control の表示契約にも直接影響します。

## 実装上の確認ポイント
- `alembic upgrade head` / rollback 手順の事前検証。
- 変更後に API 契約・bind証跡取得・Replay の基本確認。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 環境別の移行手順（分散DB、ゼロダウンタイム等）は別設計が必要です。
- 本文書だけで変更リスクを解消できるわけではありません。

## 英語正本
- [docs/en/operations/database-migrations.md](../../en/operations/database-migrations.md)
