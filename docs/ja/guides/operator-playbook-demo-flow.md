# Operator Playbook / Demo Flow（Regulated Decision Governance）

## 目的

営業同席デモ、PoC運用、監査事前説明で、
同じメッセージと同じ手順を再利用できるようにする。

## 役割

- Sales/SE: ストーリー進行と価値説明
- Operator: ケース実行と例外処理
- Reviewer/Auditor: artifact と lineage の確認

## 15分デモ構成

### Phase 1（3分）: Coexistence framing

- Runtime governance と VERITAS の責務分離を説明
- 先に「VERITAS は decision governance 層」であることを固定

話す文:
> Runtime は action execution control、
> VERITAS は decision governance と bind-boundary control を担います。

### Phase 2（5分）: ケース実行

- AML/KYC 高リスクケースを投入
- 自動承認ではなく review/deny/hold 分岐を確認
- decision artifact の理由を確認

### Phase 3（4分）: Bind artifact walkthrough

- decision artifact -> execution intent -> bind receipt を順に表示
- `execution_intent_id` と `bind_receipt_id` を読み上げて追跡可能性を示す

### Phase 4（3分）: Audit handoff

- 監査向け提出物一式を確認
- replay/revalidation 可能性を示す
- 「何が実装済みで、何が今後か」を明示

## オペレーション手順（チェックリスト）

### デモ前

- [ ] 対象ケース（正常/境界/要レビュー）を最低3件準備
- [ ] ポリシー版数・適用日時を控える
- [ ] 出力 artifact の必須ID項目を確認

### デモ中

- [ ] 1ケース目: 正常系（admissible）
- [ ] 2ケース目: 証跡不足（review required）
- [ ] 3ケース目: 明確拒否（deny/block）
- [ ] すべてで lineage 接続を実演

### デモ後

- [ ] handoff pack を共有
- [ ] buyer 側の統制要件との差分を記録
- [ ] 追加PoC項目を「実装済み/未実装」に分けて合意

## 失敗しやすい点

- runtime の広さを語りすぎて、VERITAS の差別化（bind-boundary）が薄れる
- モデル精度トークに寄りすぎ、監査受け渡しの価値が伝わらない
- 未実装 integration を「可能」ではなく「提供済み」と誤表現する

## セキュリティ/コンプライアンス注意

- ケースデモには実データを使わず、匿名化済み/合成データを使う。
- ID欠落 artifact は監査提出しない。
- 手動オーバーライド時は理由と承認者情報を必ず記録する。

## Buyer 別の1行メッセージ

- Investor: 「VERITAS は実行数ではなく、規制業務の決定統制で勝つ。」
- Customer: 「判断を実行前に拘束し、監査受け渡しできる。」
- Operator: 「例外時でも lineage を切らずに運用できる。」
