# Regulated / High-Stakes Beachhead Pack（AML/KYC・承認ワークフロー向け）

## このパックの狙い

VERITAS の販売軸を「汎用AI運用の広さ」ではなく、
**bind-boundary を伴う regulated decision governance** に固定する。

対象ユースケース:
- AML / KYC
- approval workflows（多段承認・例外承認）
- externally reviewable decisions（外部レビュー前提の意思決定）

## Why this matters（なぜ重要か）

- 高ステークス領域では「高精度」よりも**説明可能な統制境界**が買われる。
- 誤判定時の被害は、判断モデルそのものより
  「境界管理不備」「監査受け渡し不備」から増幅する。
- VERITAS は decision-to-effect の途中に bind-boundary を置くことで、
  実行前統制と事後検証を両立する。

## Demo Scenario（標準シナリオ）

### シナリオ名
AML/KYC: 高リスク送金候補の審査

### 入力例
- 顧客属性: 本人確認は完了、ただし住所証跡が古い
- 取引属性: 通常閾値を超える国際送金
- 追加証跡: 一部不足

### 期待される振る舞い
- 自動承認に流さない（fail-open を避ける）
- `REVIEW_REQUIRED` または `DENY/HOLD` 系へ遷移
- 判断根拠を decision artifact に残す
- bind 可否を明示し、receipt で境界判断を追跡可能にする

## Operator Flow（運用フロー）

1. ケース受付（case_id 付与）
2. VERITAS で decision governance 実行
3. evidence 不足/矛盾時は人手レビューへ分岐
4. bind-boundary 判定（admissible/not admissible）
5. admissible のみ runtime 側へ実行委譲
6. bind receipt と runtime 実行結果を相互参照で保存
7. 監査要求時に handoff pack を提出

## Bind Artifact Walkthrough（何を見せるか）

- `decision artifact`
  - 判断理由、関連ポリシー、入力証跡
- `execution intent`
  - 実行対象・条件・制約
- `bind receipt`
  - 境界判定結果、失敗理由コード、参照ID

監査説明では「モデルの気持ち」ではなく、
**artifact 間の因果接続**（decision -> intent -> receipt）を主語にする。

## Audit Handoff Flow（監査受け渡し）

1. ケース単位で artifact を束ねる
2. 欠落フィールド（ID、タイムスタンプ、理由コード）を検査
3. 外部監査向けにケース概要と境界判定サマリを付与
4. replay/revalidation 手順を同梱
5. 監査指摘の差分を次回ポリシー改定に反映

## Buyer向け短文（提案資料用）

> VERITAS は AML/KYC と承認ワークフローで、
> 意思決定を実行前に拘束する bind-boundary と
> 外部レビュー可能な lineage を提供します。
> runtime の実行統制を置換するのではなく、
> その前段の決定統制を監査可能にします。

## Fact Boundary（主張境界）

- 本パックは「規制業務を安全に設計・説明するための governance pack」であり、
  法的判断の自動化や規制当局認証を保証するものではない。
- runtime との連携は、実装済み経路と運用設計に依存する。
  未実装経路を既成事実として説明しない。
