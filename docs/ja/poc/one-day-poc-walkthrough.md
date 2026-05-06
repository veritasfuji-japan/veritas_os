# One-Day VERITAS PoC Walkthrough（日本語版）

> この文書は英語正本 `docs/en/poc/one-day-poc-walkthrough.md` に対応する日本語版です。仕様判断が必要な場合は英語正本を優先してください。

## 目的

本ウォークスルーは、既存機能を使って VERITAS の価値を 1 日で外部レビュー担当者へ提示するための PoC 導線です。ランタイムの意味論は変更しません。

## 対象読者

- HPAN レビュアー
- 企業側ステークホルダー／導入担当
- 監査・保証担当
- 投資家・技術 DD 担当

## この PoC で実証すること

- `GET /v1/observability/capabilities` による観測性 capability の確認
- RBAC denial audit append visibility（既存の観測・監査導線で確認可能な範囲）
- governance policy 変更に対する Human Approval Workbench の承認導線
- Bind Boundary の結果と receipt（証跡）
- governance 関連フローの trace / span chain 連続性
- 既存実装における TrustLog と監査可能性シグナル

## この PoC で実証しないこと

- 本番運用の完全な構成・ハードニング
- Jaeger / Grafana / Tempo / OTLP collector のデプロイ
- 人手承認の暗号学的署名
- 現行実装を超える TrustLog append durability 保証
- 最終的なエンタープライズ向けパッケージングや商用 SLA

この PoC の目的は、最終パッケージではなく「強制可能な境界」と「監査可能性」を示すことです。

## 前提条件

1. VERITAS API サーバーが起動済みであること。
2. observability エンドポイントを読める API キーがあること。
   - API キーは `governance_read` 権限を含む role（例: `auditor` / `admin`）に紐づいている必要があります。
3. 環境変数:
   - `VERITAS_BASE_URL`（任意、既定値 `http://127.0.0.1:8000`）
   - `VERITAS_API_KEY`（必須）
   - `VERITAS_DEMO_ALLOW_MUTATION`（任意、既定値 `false`）
4. スモークスクリプトを実行できる Python 環境。

## シナリオ A: Observability capability check

1. 実行:
   - `python scripts/demo/one_day_poc_smoke.py --json`
   - `python scripts/demo/one_day_poc_smoke.py --json --evidence-json /tmp/veritas_poc_evidence.json`
   - `python scripts/demo/one_day_poc_smoke.py --evidence-md /tmp/veritas_poc_evidence.md`
2. `capabilities_ok: true` を確認。
3. 要約に以下が含まれることを確認:
   - structured logging format
   - OpenTelemetry importability
   - exporter configured
   - governance span chain
   - RBAC denial audit append visibility

## シナリオ B: RBAC denial audit visibility

1. 標準の検証手順で RBAC deny イベントを生成または取得。
2. 既存の監査／観測導線で deny 証跡が見えることを示す。
3. 可能であれば同一 trace context でログと突合する。

## シナリオ C: Human Approval を伴う governance policy update

1. Human Approval Workbench 上の policy update 導線を説明。
2. 現行実装で 4-eyes 承認が必要であることを示す。
3. 承認記録と監査エントリを提示。
4. 承認後編集の失効（post-approval edit invalidation）挙動を示す。

## シナリオ D: Bind Boundary の結果と receipt

1. policy 適用下のアクション例を実行。
2. Bind Boundary の結果（`allow` / `deny`）と receipt を提示。
3. 結果と policy 文脈、監査証跡の対応関係を示す。

## シナリオ E: Trace/span verification

1. シナリオ B〜D のいずれか 1 リクエストを対象にする。
2. `trace_id` 伝播をリクエスト／監査ログで確認する。
3. decision から証跡出力まで governance span chain が連続していることを示す。

## 証跡チェックリスト

- [ ] `GET /v1/observability/capabilities` のレスポンス取得
- [ ] スモークスクリプト JSON 要約の取得
- [ ] 外部レビュー提出用の sanitized evidence packet（`--evidence-json` / `--evidence-md`）生成
- [ ] RBAC deny と監査可視性の例
- [ ] governance update の human approval 証跡
- [ ] Bind Boundary の結果と receipt サンプル
- [ ] trace_id と governance span chain 連続性の証明
- [ ] 制約・非目標をレビューパケットに明記

## 成功条件

- 外部レビュアーが内部知識なしで順番に確認できる。
- observability capability シグナルを第三者が検証できる。
- RBAC / human approval / bind boundary / trace continuity の証跡を確認できる。
- デモのために runtime の governance/bind/RBAC/TrustLog 意味論を変更しない。

## 既知の制約

- 本番参照アーキテクチャではない。
- Jaeger/Grafana/Tempo/OTLP collector の構築は含まない。
- 暗号学的な human approval 署名は含まない。
- TrustLog durability 特性は現行実装のままである。
- スモークツールの mutation 経路は既定で無効。
- evidence packet は PoC 証跡用であり、本番認証（production certification）ではない。

## Evidence packet の内容と非包含項目

one-day smoke script は、外部共有向けに sanitize 済み evidence packet を生成できます。

- `--evidence-json PATH`: 構造化 JSON evidence packet を出力
- `--evidence-md PATH`: レビュアー向け Markdown packet を出力

含まれるもの:

- observability capability の allowlist 要約シグナル
- observability と governance policy read の read-only チェック結果
- ドキュメント参照リンクと PoC 非目標の明示

含まれないもの:

- API キーおよび `X-API-Key` の値
- raw exporter endpoint URL
- raw 環境変数値
- raw request/response payload 本文
- token / cookie / password / secret / authorization header

## 外部レビュアー向け推奨トークトラック

1. 「このデモは本番ローンチではなく、境界強制と監査可能性の提示です。」
2. 「まず capability 面と logging/trace 制御面を確認します。」
3. 「次に RBAC deny 可視性と、人手承認（4-eyes・承認後編集失効）を確認します。」
4. 「続いて bind outcome と receipt を trace 証跡と結び付けて確認します。」
5. 「最後に、1-day PoC の意図的な非対象範囲を明示します。」
