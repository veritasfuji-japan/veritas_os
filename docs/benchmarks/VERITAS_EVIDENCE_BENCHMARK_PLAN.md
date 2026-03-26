# VERITAS OS Evidence Benchmark Plan

## 1. Purpose

この計画は、VERITAS OS の強みを「主観的な説明」ではなく、
**再現可能なベンチマーク証跡**で示すためのものです。

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
- system A: `veritas`（VERITAS OS 出力）
- system B: `generic`（generic agent loop 出力）

同一ケースを両者で評価し、同一メトリクスで比較する。

### 3.2 Dataset / Fixture
- 形式: JSONL
- 1行1ケース
- 各ケースに `systems.veritas` と `systems.generic` の観測結果を埋める

これにより、API 実行済みログを後からオフライン評価可能。

### 3.3 Output Format
- JSON（`veritas_os/benchmarks/evidence/output_schema.json` で定義）
- 集計 (`aggregate`) とケース単位 (`cases`) を両方保存

## 4. Reproducibility Rules

- ハーネス入力（fixtures）を Git 管理し、同一入力で同一出力を得る。
- 計算式を `metrics_definition.yaml` に明記する。
- 推定値や外挿値を禁止し、観測できるキーのみを判定に使う。

## 5. Security Warnings

- フィクスチャに生ログを入れる場合は PII を必ず除去する。
- trust log 系の実データは改ざん防止目的のため、テスト用コピーを使う。
- 署名検証を伴うデータを共有する場合は鍵情報を含めない。

## 6. Execution

```bash
python -m veritas_os.scripts.evidence_benchmark \
  --fixtures veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl \
  --output veritas_os/scripts/logs/evidence_benchmark_report.json
```

## 7. Publishable Summary Template

- 「Xケース中、Fail-Closed要件を満たした割合」
- 「監査可能性（必須監査キー充足率）」
- 「Replay差分可視化率」
- 「Trust Log整合性キー充足率」

上記を `veritas` と `generic` で並列表記する。
