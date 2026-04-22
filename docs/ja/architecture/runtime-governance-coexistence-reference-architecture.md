# Runtime Governance Layer と VERITAS 共存の Reference Architecture

## 目的

この文書は、`runtime governance layer` と `VERITAS` を競合関係ではなく**責務分離された共存構成**として提示する。
市場メッセージは「実行制御の広さ」ではなく、**decision-to-effect の深さ**と
**bind-boundary の検証可能性**に固定する。

## 先に結論（Buyer向け30秒版）

- Runtime governance は「**action execution controls**」を担当する。
- VERITAS は「**decision governance + bind-boundary control + replayable lineage**」を担当する。
- 両者を分離すると、実行前の意思決定品質と実行時の強制制御を同時に成立させられる。

## 責務分離

### 1) Runtime governance の責務（実行制御）

- 実行主体（agent/tool/job）の認可・制限
- 実行時ポリシー（allow/deny/throttle/kill-switch）
- シークレット・ネットワーク・エグレス等の実行面ガード
- 実行ログ・監査ログの収集

> ここは「何を実行させるか / 止めるか」の層。

### 2) VERITAS の責務（意思決定統制）

- 意思決定前の evidence/critique/debate/fuji を含む decision governance
- decision artifact から execution intent への bind-boundary 判定
- bind receipt を含む tamper-evident lineage
- replay/revalidation による外部レビュー可能性

> ここは「なぜその判断を採ったか」「その判断をどの境界条件で実世界効果へ接続したか」の層。

## 共存アーキテクチャ（論理図）

```text
[Case Intake / Request]
          |
          v
[VERITAS Decision Governance]
  evidence -> critique -> debate -> policy/bind check
          |
          |  decision artifact
          v
[VERITAS Bind-Boundary Control]
  decision artifact -> execution intent -> bind receipt
          |
          |  admissible intent only
          v
[Runtime Governance Layer]
  execution authorization / isolation / kill switch / runtime audit
          |
          v
[External Effect System]
  payment, account state change, notification, filing, etc.
```

## Interface Contract（共存時に固定すべき最小契約）

1. **Boundary Input**
   - Runtime 側へ渡す前に `execution_intent_id` を必須化
   - 意思決定根拠は `decision artifact` 参照で追跡可能にする
2. **Boundary Output**
   - 実行可否/失敗理由を `bind_outcome` / `bind_reason_code` と整合させる
3. **Audit Linkage**
   - `bind_receipt_id` と runtime event id の相互参照を保持
4. **Replayability**
   - 同一ケースを再評価したとき、境界判定の再検証が可能であること

## 導入時の誤解を避ける文言

### 言ってよい

- 「VERITAS は runtime を置換せず、意思決定統制を前段で強化する」
- 「runtime は実行統制、VERITAS は決定統制と bind-boundary を担う」

### 言ってはいけない

- 「VERITAS が runtime execution control を全面代替する」
- 「すべての外部実行経路と完全統合済み」

## セキュリティ観点（共存設計での注意）

- 境界ID（`execution_intent_id`, `bind_receipt_id`）を runtime 連携で欠落させると、
  decision-to-effect の追跡が切断される。
- runtime 側で実行を許可した後に bind 情報を後付けする運用は、
  監査整合性を損なうリスクがある。
- 例外系（timeout/retry/manual override）で lineage を欠落させると
  externally reviewable decisions の要件を満たせない。

## 市場ストーリーへの接続

- breadth 競争: 「何でも実行できる runtime 機能追加」
- VERITAS の勝ち筋: 「**高ステークス意思決定を監査可能な境界で拘束する深さ**」

このため、提案資料は常に「実行機能一覧」より先に
**bind-boundary と replayable lineage** を示す。
