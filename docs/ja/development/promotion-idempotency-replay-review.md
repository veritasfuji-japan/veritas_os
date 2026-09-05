# Promotionの冪等性・再利用防止レビュー

Runtime Risk Review通過後、
`veritas_os.policy.live_adapter_bind_authorization_requirements` の
`review_promotion_idempotency_and_replay` にリスク評価packet、その完全な
最終credential-scopeソース、タイムゾーン付き`reviewed_at`を渡します。
ソースを独立検証し、リスク評価の記録時刻以降かつ失効時刻より前であることを確認します。

戻り値は`model_dump(mode="json")`でシリアライズできます。
`verify_promotion_idempotency_replay_review`に両ソースと信頼できる現在時刻`now`を
渡すと、全フィールドを再構築し、有効期限も再確認します。
ハッシュは署名や未使用の証明ではありません。

本段階は再利用防止の要件と既存の実装担当を確認します。ストア照会やキー予約は行いません。
最終キーの発行には署名済み承認判断と有効期間が必要で、既存の
`live_adapter_bind_authorization_checks`が担当します。
資格情報取得・送信前の原子的な一回限りの消費と、Bind時のリスク再確認は引き続き必須です。
通過後は署名付きgate-bound人間承認の発行へ進めますが、実行権限は付与しません。

呼び出し可能な合成用境界であり、ランタイムへの自動統合ではありません。
`test_promotion_idempotency_replay_review.py`でシリアライズ、改ざん、
リスク拒否・欠落、有効期限境界を検証します。
