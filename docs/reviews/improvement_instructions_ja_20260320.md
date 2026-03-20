# VERITAS OS 今後の改善指示

作成日: 2026-03-20
参照:
- `docs/reviews/precision_code_review_ja_20260319.md`
- `docs/reviews/precision_code_review_ja_20260319_reassessment.md`
- `docs/architecture/core_responsibility_boundaries.md`

## 目的

本指示書は、最新レビューで確認された残課題に対して、
**責務境界を越えず**、かつ**安全性・監査性・保守性を下げない**範囲で
今後の改善優先順位を明確化するためのものです。

対象は主に以下の継続課題です。

- `pipeline.py` / `kernel.py` / `fuji.py` / `memory.py` に集中している構造的複雑度
- compatibility layer と正規拡張ポイントの見分けにくさ
- degraded 状態の運用手順の不足
- fail-open や optional dependency に関する運用事故リスク

## 絶対条件

以下は今後の改善で必ず守ること。

1. Planner / Kernel / FUJI / MemoryOS の責務境界を越えない。
2. public contract を壊す変更は、別レビューと明示的承認なしに行わない。
3. compatibility layer を削る場合は、既存テストと利用経路への影響を先に明示する。
4. 重大な変更には docstring と回帰テストを必ず追加する。
5. degraded / fail-open / fallback を扱う変更では、運用者が観測可能な warning または structured status を維持する。

## 優先順位

## Priority 1: 中核複雑度の抑制

### 指示 1-1. 正規拡張ポイントの入口を中核モジュール冒頭でより明示する

`pipeline.py` / `kernel.py` / `fuji.py` / `memory.py` の module docstring または
冒頭コメントに、次を簡潔に明記すること。

- このモジュールの public contract
- 新規ロジックを追加すべき helper / stage module
- compatibility layer の存在と、その扱い方

目的は、アーキテクチャ文書を読まなくても、
大型モジュールに直接分岐を足す前に正規拡張ポイントへ誘導できるようにすることです。

### 指示 1-2. compatibility-heavy な処理は helper へ逃がす

新しい条件分岐・データ整形・fallback を追加する場合、
まず既存 helper / stage module に置けないかを確認してください。

特に以下を優先候補とします。

- Pipeline: `pipeline_*` 系サブモジュール
- Kernel: `kernel_stages.py`, `kernel_qa.py`, `pipeline_contracts.py`
- FUJI: `fuji_policy.py`, `fuji_policy_rollout.py`, `fuji_helpers.py`, `fuji_safety_head.py`
- MemoryOS: `memory_helpers.py`, `memory_search_helpers.py`, `memory_summary_helpers.py`, `memory_lifecycle.py`, `memory_security.py`, `memory_store.py`

**禁止**:
- 便宜上の理由だけで中核本体へ新規責務を直書きすること
- Planner / Kernel / FUJI / MemoryOS 間で責務を横滑りさせること

## Priority 2: 運用 observability の強化

### 指示 2-1. TrustLog degraded 状態の runbook を作成する

以下を最低限含む runbook を作成してください。

- `trust_json_status=unreadable|invalid|too_large` の意味
- 監査上の影響
- 初動確認手順
- 復旧手順
- 再発防止の確認項目

重要なのは、現実装は「上書き破壊を防ぐ」ものであり、
**自動修復ではない**点を明文化することです。

### 指示 2-2. fail-open 設定の検知経路を整理する

`VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は local/test 系に限定されていても、
shared staging / preview に残ると運用事故の温床になります。

今後は以下を順に整備してください。

- startup warning の確認手順
- CI または deployment check による検知
- 環境別の許容/禁止ポリシーの文書化

**セキュリティ警告**:
fail-open は非本番でも認証保護を弱めるため、
共有環境に残置しないこと。

## Priority 3: 例外契約の精密化

### 指示 3-1. Memory API の段階別失敗理由を将来的に細分化する

現状の `partial_failure` と `errors[]` は有用ですが、
今後さらに監査要件を強めるなら、少なくとも次の区別を検討してください。

- validation failure
- backend unavailable
- security/policy rejection
- serialization or storage failure

ただし、この改善では response contract の互換性を壊さないようにし、
既存の `ok / status / errors[]` を維持したうえで拡張してください。

### 指示 3-2. broad exception は段階的に縮小する

即時全面置換ではなく、影響の大きい箇所から段階的に行うこと。
その際は以下を満たしてください。

- ログがノイズ過多にならないこと
- API 利用者に必要な失敗分類が見えること
- fail-closed / degraded 設計を崩さないこと

## Priority 4: capability matrix の明文化

### 指示 4-1. 本番推奨 capability profile をドキュメント化する

`fuji.py` や `memory.py` には optional dependency と fallback が多く、
可搬性の利点がある一方で、環境差による非決定性の温床にもなります。

そのため、少なくとも以下を文書化してください。

- production 推奨設定
- local/test でのみ許容する設定
- strict mode を推奨する箇所
- fallback が作動したときの観測方法

## 実装ルール

改善を実装する際は、以下を開発ルールとして適用します。

- 変更は最小差分にする
- PEP8 に準拠する
- 重大な変更では docstring を追加または更新する
- 重大な変更ではユニットテストまたは回帰テストを追加する
- セキュリティ影響がある場合は warning / 文書 / テストのいずれかで必ず固定する

## 完了条件

各改善タスクは、少なくとも以下を満たしたときに完了とみなします。

1. 責務境界を越えていない。
2. 既存 public contract を破壊していない。
3. docstring / テスト / 関連文書が更新されている。
4. degraded / fallback / fail-open に関する観測可能性が後退していない。
5. 追加したガイダンスが CI またはレビュー時に再利用可能な形で残っている。

## 実務上の結論

今後の改善で最も重要なのは、機能追加の量ではありません。
重要なのは、**中核モジュールの複雑度をこれ以上増やさず、
正規拡張ポイント・運用手順・失敗観測性を強化すること**です。

つまり、次の改善フェーズでは以下を原則とします。

- 大きく作り変えるより、責務境界を守った小さな改善を積む
- 中核本体に処理を足す前に helper / stage へ逃がす
- セキュリティ上の degraded 状態は「黙って通す」のではなく観測可能に保つ
- shared 環境で fail-open を許さない


## 実施記録（2026-03-20）

### 今回完了した改善
- **Priority 1 / 指示 1-1**: `pipeline.py` / `kernel.py` / `fuji.py` / `memory.py` の module docstring を更新し、public contract・推奨拡張ポイント・compatibility layer の扱いを明示した。
- **Priority 1 / 指示 1-1 の回帰防止**: `scripts/architecture/check_responsibility_boundaries.py` を拡張し、上記 4 モジュールの docstring に required marker と推奨拡張ポイントが残っているかを CI 向けに検査できるようにした。対応する回帰テストも追加した。
- **Priority 2 / 指示 2-1**: `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` に TrustLog degraded 状態 (`trust_json_status=unreadable|invalid|too_large`) の運用 runbook を追加した。
- **Priority 2 / 指示 2-2**: 同 runbook に `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` の startup warning / fail-fast / CI・deployment check / 環境別ポリシーを追記した。

### 今回あえて実施しなかった改善
- **Priority 1 / 指示 1-2 以降** の helper 分離や例外契約拡張は、既存 public contract・責務境界・回帰範囲への影響が相対的に大きいため、今回の最小差分では未着手とした。
- **Priority 4 capability profile** は有用だが、まず中核モジュールの入口明示と degraded / fail-open runbook のほうが優先度が高いため後続タスクへ残す。

### セキュリティ警告
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は local / isolated test 限定の危険フラグであり、shared staging / preview / production へ残置すると auth store 障害時の防御低下を招く。
