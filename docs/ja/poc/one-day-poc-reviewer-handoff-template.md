# One-Day PoCレビュー引き渡しテンプレート

- 英語版が正本であり、日本語版は補助説明です。
- これはOne-Day PoC後にレビュー担当者へ渡すためのhandoff templateである。
- 何を実行し、どの証跡を収集し、何が成功し、何が失敗し、何が未解決かを整理する。
- One-Day PoC証跡パックおよびOne-Day PoC運用Runbookを補完する。
- 本番SLAではない。
- 第三者認証ではない。
- 明示的に別途記録しない限り、顧客環境測定ではない。
- EU AI Act準拠を認証するものではない。
- 外部LLM/provider latencyやcostは、明示的にproviderを有効化して別途記録しない限り測定対象ではない。

## 英語正本

- [One-Day PoC Reviewer Handoff Template](../../en/poc/one-day-poc-reviewer-handoff-template.md)

## Purpose

- One-Day PoC後のレビュー引き渡し形式を標準化する。
- PoC証跡を点検しやすくする。
- 収集済み証跡に基づく範囲に主張を限定する。

## Handoff summary

- PoC date:
- Operator:
- Reviewer / organization:
- Repository:
- Commit SHA:
- Environment type: local / configured / customer-managed
- External providers enabled: yes / no / unknown
- Evidence folder:
- Overall result: pass / fail / inconclusive

## PoC scope

- [ ] Missing authority/evidence block path reviewed
- [ ] Allowed path reviewed where applicable
- [ ] Audit/TrustLog path reviewed
- [ ] Local deterministic metrics referenced
- [ ] HTTP PoC benchmark run if in scope
- [ ] Non-claim boundaries explained
- [ ] Open questions documented

## Environment and commit

- Date/time:
- Commit SHA:
- Branch or tag:
- Local/configured/customer-managed environment note:
- API server status if HTTP flow was used:
- Whether external providers were enabled:
- Whether secrets or customer data were used:
- Redaction status:

## Scenarios reviewed

| Scenario | Expected behavior | Observed result | Evidence link | Status |
|---|---|---|---|---|
| Missing authority/evidence blocks sensitive action before commit | | | | |
| Allowed action proceeds when required evidence is present | | | | |
| Audit/TrustLog path remains reviewable | | | | |
| Deterministic local metrics reviewed | | | | |
| HTTP PoC benchmark reviewed if run | | | | |
| Non-claim boundaries explained | | | | |

## Evidence provided

| Evidence item | File/path | Required? | Notes |
|---|---|---|---|
| Environment notes | | Yes | |
| Commands run | | Yes | |
| Screenshots | | Conditional | |
| JSON evidence output | | Conditional | |
| Markdown evidence report | | Conditional | |
| Local deterministic metrics artifact | | Recommended | |
| One-Day PoC benchmark output if run | | Conditional | |
| Redaction notes | | Conditional | |
| Reviewer notes | | Yes | |

## Results summary

- Overall status: pass / fail / inconclusive
- Block path status:
- Allow path status:
- Audit path status:
- Evidence completeness:
- Reviewer confidence:
- Follow-up required:

## Known limitations

- Local/configured PoC output is not production latency.
- Local/configured PoC output is not production availability.
- Local deterministic metrics are not customer-environment measurements.
- Benchmark output is only one input into the evidence package.
- Legal, security, and regulatory review remain separate.
- Provider latency/cost is out of scope unless explicitly enabled and separately recorded.

## Non-claim boundaries

- Do not claim production SLA from this handoff.
- Do not claim third-party certification.
- Do not claim customer-environment measurement unless the PoC was actually run in that environment and documented.
- Do not claim EU AI Act compliance certification.
- Do not claim provider cost/latency unless providers were explicitly enabled and separately measured.
- Do not present demo screenshots as production audit evidence.

## Open questions and follow-up

| Question / follow-up | Owner | Due date | Status |
|---|---|---|---|
| | | | |

## Reviewer acknowledgement

- Reviewer name:
- Organization:
- Date:
- Acknowledgement:
  - [ ] I reviewed the provided evidence.
  - [ ] I understand the stated non-claim boundaries.
  - [ ] I understand this handoff does not certify production readiness or legal compliance.

## Related documents

- [`docs/ja/poc/one-day-poc-evidence-pack.md`](one-day-poc-evidence-pack.md)
- [`docs/ja/poc/one-day-poc-operator-runbook.md`](one-day-poc-operator-runbook.md)
- [`docs/ja/poc/one-day-poc-reviewer-pack.md`](one-day-poc-reviewer-pack.md)
- [`docs/ja/poc/one-day-poc-walkthrough.md`](one-day-poc-walkthrough.md)
- [`docs/ja/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md)
- [`docs/en/benchmarks/local-performance-metrics.latest.md`](../../en/benchmarks/local-performance-metrics.latest.md)
- [`docs/en/benchmarks/performance-metrics.md`](../../en/benchmarks/performance-metrics.md)
- [`docs/INDEX.md`](../../INDEX.md)
- [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md)
