# RSA ↔ VERITAS AML/KYC サンドボックス・インターフェース契約

## 位置づけとスコープ

このインターフェースは **サンドボックス専用のフィクスチャ契約** です。

- 決定論的なテストとレビュー用途を目的とします。
- RSA は外部の上流システムとして扱われ、VERITAS の中核ロジックには統合しません。
- VERITAS は RSA 形式のフラグを上流シグナルとして受け取り、継続可否・bind-boundary 判定・最終コミット結果・監査記録を下流で決定します。
- VERITAS はこの契約で `sandbox_commit_state` を出力しますが、これはサンドボックス専用の状態値です。

## 英語正本

- [English authoritative version](../../en/guides/rsa-veritas-aml-kyc-sandbox-interface.md)

## 現在のサンドボックス・マッピング

RSA の上流フラグを、VERITAS の継続判断へ次のように対応付けます。

- `SAFE_PROCEED` → `CONTINUE_TO_BIND_BOUNDARY`
- `DENSITY_THROTTLED` → `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED`
- `ALGORITHMIC_HUMILITY_ENGAGED` → `PAUSE_FOR_HUMAN_REVIEW`
- `DEFERRAL_ENGAGED` → `BLOCK_FINAL_COMMIT`

サンドボックスのコミット状態値:

- DEFERRAL 以外の経路 → `SUSPENDED_NOT_COMMITTED`
- DEFERRAL 経路 → `BLOCKED_NOT_COMMITTED`

`sandbox_commit_state` はサンドボックス用のフィクスチャ状態であり、本番の bind receipt outcome / bind outcome の正規語彙ではありません。

## 免責事項

この成果物は **本番 AML/KYC コンプライアンス実装ではありません**。

この成果物は **規制当局による承認ではありません**。
この成果物は **第三者認証ではありません**。
この成果物は **法的助言ではありません**。

## セキュリティノート

これはサンドボックス専用のため、このフィクスチャ単体を本番 AML/KYC ゲートとして利用してはいけません。本番運用では、独立に検証されたポリシー制御・authority evidence 検証・監査可能な法務/規制レビューが必要です。
