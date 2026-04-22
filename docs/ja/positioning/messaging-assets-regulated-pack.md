# Messaging Assets Kit（Investor / Customer / Operator）

## 目的

buyer別に同じ核（bind-boundary と regulated decision governance）を保ったまま、
短文で再利用できるメッセージ資産を提供する。

## Core Message（全員共通）

VERITAS は runtime を置換する製品ではない。
**意思決定を実行前に拘束し、外部レビュー可能な lineage を残す governance layer** である。

## 1) Investor向け

### 15秒版

VERITAS は AI の breadth 競争ではなく、
高ステークス意思決定の bind-boundary 統制で差別化する。

### 60秒版

多くのAI基盤は「どれだけ実行できるか」を競う。
VERITAS は「どの意思決定を、どの条件で実行へ接続したか」を
再現可能に証明する。AML/KYC や承認業務のような規制領域では、
この監査可能性が導入決裁の主要要件になる。

### 禁止表現

- 「すべての enterprise runtime を代替」
- 「全面的な規制準拠を保証」

## 2) Customer向け

### 15秒版

VERITAS は、重要判断を実行前に bind-boundary で拘束し、
監査提出までを一気通貫で支援する。

### 60秒版

高リスクケースを単純自動承認に流さず、
review/deny/hold に分岐させる統制設計を実装できる。
さらに decision artifact / execution intent / bind receipt の系譜を残すため、
監査・内部統制・事故調査で説明可能性を維持できる。

### FAQ短答

- Q: Runtimeは必要ですか？
  - A: はい。runtime は実行統制、VERITAS は決定統制を担います。
- Q: 既存基盤を捨てる必要がありますか？
  - A: いいえ。共存前提で導入できます。

## 3) Operator向け

### 15秒版

VERITAS は例外時でも lineage を切らない運用を支援する。

### 60秒版

運用者は「判定」「境界」「実行」を分離して扱える。
証跡不足時はレビューに戻し、admissible な意図のみ実行へ渡す。
結果として、障害時や監査時にケースを replay/revalidation しやすくなる。

### 現場で使う言い回し

- 「まず判定を固定、次に境界を固定、最後に実行へ渡す」
- 「実行結果の前に、実行可能性の根拠を残す」

## Pitch Deck に入れる1枚（推奨構成）

1. 課題: 高ステークス業務で decision-to-effect が不透明
2. 分離: runtime execution control と decision governance を分ける
3. VERITAS: bind-boundary + replayable lineage
4. 適用: AML/KYC / approval workflows / externally reviewable decisions
5. 主張境界: 実装済み経路とロードマップを明確分離

## One-liner Library（再利用短文）

- 「VERITAS is the bind-boundary governance layer before execution.」
- 「We compete on decision-to-effect depth, not runtime breadth.」
- 「For regulated workflows, reviewability beats raw automation speed.」

## Security / Trust 注意書き（外部説明用）

- 実データ利用時は最小権限・最小開示を徹底する。
- デモ・検証では匿名化済みデータを使う。
- 監査資料はケース単位でアクセス制御し、配布先を記録する。
