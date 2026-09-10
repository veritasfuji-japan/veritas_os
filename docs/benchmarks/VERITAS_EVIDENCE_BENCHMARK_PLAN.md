# VERITAS OS Evidence Benchmark Plan

## 1. Purpose

この計画は、VERITAS OS の強みを「主観的な説明」ではなく、
**再現可能なベンチマーク証跡**で示すためのものです。

TASK-011 Benchmark Rebaselineでは、
`docs/benchmarks/benchmark-rebaseline-contract-v1.json`
をベンチマークの正本契約として扱います。

対象の差別化軸:

1. auditability
2. fail-closed safety
3. governance change control
4. replay / divergence visibility
5. trust log integrity

## 2. Differentiation Axes and Test Intent

### A. Auditability
- 検証したいこと: 意思決定ごとに、第三者が追跡可能な監査情報が残るか。
- 最小要件:
  - request_id / decision_id の一意識別子
  - evidence_count など根拠の計数
  - timestamp

### B. Fail-Closed Safety
- 検証したいこと: 不確実・高リスク時に「通す」のではなく安全側（hold/deny）へ倒れるか。
- 最小要件:
  - `expected.fail_closed_on_uncertainty=true` のケースで decision が hold/deny

### C. Governance Change Control
- 検証したいこと: ポリシー変更が承認付きで追跡できる形で反映されるか。
- 最小要件:
  - policy_version
  - change_ticket_id
  - approval_count >= 1（policy_changed=true の時）

### D. Replay / Divergence Visibility
- 検証したいこと: 再実行時に差分と重大度が可視化されるか。
- 最小要件:
  - replay 実行可否
  - diff.changed / divergence_level

### E. Trust Log Integrity
- 検証したいこと: 監査ログが改ざん検出可能なチェーン整合性を持つか。
- 最小要件:
  - sha256
  - sha256_prev
  - signature_valid

## 3. Benchmark Design

### 3.1 Comparison Target
- system A: `veritas`（VERITAS OS fixture）
- system B: `generic`（generic agent loop fixture）

同一ケースを両者で評価し、同一メトリクスで比較する。

**重要なclaim boundary:**
現在の `sample_cases.jsonl` にある `veritas` / `generic` は、
repository内で管理されたsynthetic fixtureである。
この結果を、独立第三者による競合検証、実製品比較、またはnamed vendorに対する優位性の証明として扱ってはならない。

### 3.2 Dataset / Fixture
- 形式: JSONL
- 1行1ケース
- 各ケースに `systems.veritas` と `systems.generic` の観測/fixture結果を埋める
- TASK-011 Phase A時点のcanonical fixture: `veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl`
- Phase A時点では2ケース

これにより、同じfixtureに対してオフラインで再評価できる。

### 3.3 Output Format
- JSON（`veritas_os/benchmarks/evidence/output_schema.json` で定義）
- 集計 (`aggregate`) とケース単位 (`cases`) を両方保存

## 4. Reproducibility Rules

- ハーネス入力（fixtures）を Git 管理し、同一入力で同一評価を得る。
- 計算式を `metrics_definition.yaml` に明記する。
- 推定値や外挿値を禁止し、観測できるキーのみを判定に使う。
- Current-headとして公開するartifactはsource commit SHAを記録する。
- exact command / runtime identity / fixture identity / claim boundaryを記録する。

## 5. Security Warnings

- フィクスチャに生ログを入れる場合は PII を必ず除去する。
- trust log 系の実データは改ざん防止目的のため、テスト用コピーを使う。
- 署名検証を伴うデータを共有する場合は鍵情報を含めない。
- Benchmark実行のために外部LLM/APIを暗黙に有効化しない。

## 6. Execution

TASK-011 canonical command:

```bash
python -m veritas_os.scripts.evidence_benchmark \
  --fixtures veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl \
  --output /tmp/veritas-evidence-benchmark.json
```

## 7. Publishable Summary Template

公開可能なのは、synthetic fixtureであることを明記した上での以下の記述です。

- 「Xケース中、Fail-Closed要件を満たした割合」
- 「監査可能性（必須監査キー充足率）」
- 「Replay差分可視化率」
- 「Trust Log整合性キー充足率」

`veritas` と `generic` の並列表記は可能ですが、
**synthetic fixture comparison** と明示し、第三者競合benchmarkのように表現しません。

## 8. TASK-011 Phase A Boundary

Phase Aでは新しいbenchmark数値を公開しません。

先に固定するもの:

- canonical harness
- metrics definition
- fixture/input identity
- output schema
- exact command
- source commit identity
- environment requirements
- claim / non-claim boundary

Current-head数値の生成はPhase Bで行います。
