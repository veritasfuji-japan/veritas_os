# Governance Trace Span Chain（ガバナンストレース span chain）

> この文書は日本語の解説版です。仕様上の正本（canonical source）は英語版 `docs/en/operations/governance-trace-span-chain.md` です。

## 目的

本書は、VERITAS OS のガバナンスポリシー更新経路で現在どこまでトレースできるか、どの属性が安全に利用可能か、何が未実装かを明確にし、外部レビュアー・HPAN・企業監査担当の確認を容易にすることを目的とします。

## 実装済みの範囲

現時点で実装されている内容:

- OpenTelemetry 互換の tracing helper（fail-safe な no-op fallback 付き）
- API middleware の root span
- governance policy update の span chain
- RBAC denial の span event 出力
- span 有効化後に属性を付与する実装

## governance policy update で期待される span chain

`PUT /v1/governance/policy` で確認すべき span / event は以下です。

1. `http.request`（middleware root span）
2. `governance.policy_update.request`
3. `governance.approval.validate`
4. `governance.bind_boundary.evaluate`
5. `bind.boundary.evaluate.start`（event）
6. `bind.boundary.evaluate.end`（event）
7. `governance.policy.persist`
8. `governance.policy_update.response`

補足:

- `bind.boundary.evaluate.start` / `bind.boundary.evaluate.end` は bind evaluator 側の event で、レビュー時には boundary 評価ライフサイクルの検証対象として扱います。

## RBAC denial で期待される event

RBAC が権限不足を拒否した場合、アクティブ span に次の event が付与されます。

- `rbac.denied`
- `rbac.denial.audit_append`

この event には role / permission / endpoint / method / reason code / trace id などの拒否メタデータのみを記録し、秘密情報は含めません。
`rbac.denial.audit_append` では `audit_append_status = success | failed | deduped` により、best-effort な TrustLog 追記結果のみを可視化します（RBAC deny の意味論や API 応答は変更しません）。

## プライバシー安全属性ポリシー

トレース情報は運用監査に必要な可観測性を維持しつつ、秘密情報や個人情報の漏えいを避ける必要があります。

## 現在期待される attributes

実装とテストで現在確認対象となるキー:

- `trace_id`
- `http.method`
- `http.route`
- `veritas.component`
- `status_code`
- `decision_id`
- `request_id`
- `actor_identity`
- `policy_snapshot_id`
- `approval_count`
- `bind_receipt_id`
- `final_outcome`
- `bind_reason_code`
- `target_path`
- `target_type`
- `event_type`
- `reason_code`
- `actor_role`
- `requested_permission`
- `endpoint`
- `method`
- `audit_append_status`
- `error_type`

## 明示的に禁止される attributes

次の項目は span attributes / events に**絶対に**含めてはいけません。

- `Authorization`
- `X-API-Key`
- `Cookie`
- `token`
- `secret`
- `password`
- raw request body
- `query_string`
- personally identifying free-text payloads
- approval signature raw secret beyond existing v1 token string semantics
- medical/financial record contents

## no-op fallback の挙動

tracing helper は fail-safe 設計です。

- OpenTelemetry が利用できない場合、helper は no-op として動作します。
- tracing API で障害が起きても、業務ロジックは継続します。
- そのため、OpenTelemetry や exporter 未設定は governance / bind / RBAC の意味論を変更しません。

## 現在の非目標（未実装）

本スコープ外（未実装）:

- Jaeger deployment
- Grafana/Tempo dashboard
- OTLP exporter configuration
- production collector
- cryptographic human approval signature
- backend TrustLog append guarantee changes
- full distributed tracing across external services
- frontend visual trace viewer

## ローカル検証手順

重要:

- OpenTelemetry exporter がない環境では、span が no-op になるか、外部 trace UI に表示されない場合があります。
- 現時点の検証は unit tests / fake tracer / monkeypatch tests が中心です。

実行コマンド:

- `pytest -q veritas_os/tests/test_trace_span_chain.py`
- `pytest -q veritas_os/tests/unit/test_auth_rbac_audit.py`
- `pytest -q veritas_os/tests/test_middleware_core.py`

## 外部レビュアーチェックリスト

1. governance update 経路で期待 span 名と boundary event が出ることを確認する。
2. RBAC denial で `rbac.denied` event が安全な属性で出ることを確認する。
3. 監査に必要な privacy-safe attributes が確認できることを確認する。
4. 禁止 attributes が span attributes/events に含まれないことを確認する。
5. no-op fallback の挙動が文書化され、テストで担保されていることを確認する。
6. 本PRに Jaeger/Grafana/OTLP のデプロイ作業が含まれないことを確認する。

## Runtime observability capabilities endpoint

`GET /v1/observability/capabilities` を使うと、現在環境の observability / auditability capability を read-only で確認できます。

セキュリティ境界:
- exporter 設定は boolean のみ返します。
- endpoint URL、token、API key、secret の生値は返しません。

この endpoint では、環境によって Jaeger/Grafana/OTLP 関連項目が non-goal / not configured として返る場合があります。
