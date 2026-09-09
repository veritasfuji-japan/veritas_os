# Controlled Execution Proof Architecture Freeze v1

Status: **FROZEN CONTROLLED PROOF SCOPE**

Freeze anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`  
Proof PR: #2215  
Required proof check: `reproducible-decision-to-effect-e2e`

Machine-readable contract:
[`docs/architecture/controlled-execution-proof-freeze-v1.json`](../../architecture/controlled-execution-proof-freeze-v1.json)

## 1. 目的

この文書は、freeze PRより前に成立した**controlled current-head
Decision-to-Effect sandbox proof architecture**を固定します。

目的はVERITASをproduction-readyと宣言することではありません。
次のLarge Consolidation Auditでduplicate implementation、dead path、
不要なabstractionを削除するときに、実際に証明済みのsemanticsを
知らないうちに変えないためのtechnical baselineを作ることです。

freeze対象は意図的に限定します。repository全体、将来の全adapter、
全production deploymentを固定するものではありません。

## 2. Frozen proof chain

固定するproof pathは次です。

`POST /v1/decide`
→ verified CanonicalDecisionArtifact
→ deterministic promotion
→ native v2 authorization
→ PostgreSQL single-use consumption
→ current governance rechecks
→ exact sandbox action / endpoint / credential binding
→ credential resolution
→ durable dispatch intent
→ at-most-once certificate-validated TLS transport
→ synthetic sandbox event persistence
→ `EFFECT_UNKNOWN`
→ independent read-only reconciliation
→ durable reconciliation archive
→ BindReceipt / Outcome
→ crash recovery
→ machine-readable normal/fault proof artifacts

各stageは元のdecisionとexact execution intentへlineageを保ちます。

## 3. Frozen safety semantics

次の意味をfreeze contractとします。

1. Authorization issuanceはexecution permissionではない。
2. sandbox execution attemptの前にsingle-use consumptionが必要。
3. effect前にcurrent governance / risk / authority / approvalを再確認する。
4. transport開始前にdispatch intentをdurableに保存する。
5. `EFFECT_UNKNOWN`はfailureではなくuncertainty stateである。
6. missing / 404 / unavailable lookupはno-effectの証明ではない。
7. effectの可能性がある状態からblind redispatchしない。
8. 同じbusiness eventはunresolvedまたはconfirmedの間replacementをblockする。
9. reconciliationはread-onlyでpersisted effectを独立確認する。
10. BindReceipt / Outcomeはretrospective evidenceであり新しいauthorityではない。
11. crash recoveryはexternal effectを再送しない。
12. Decision → authorization → consumption → effect → receipt/outcome lineageを
    検証可能なまま保つ。

## 4. Freeze anchorとproof evidence

baselineはPR #2215のmain merge commitです。

`ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

merge前に39 checksが全てPASSし、専用
`reproducible-decision-to-effect-e2e` workflowもPASSしました。
workflowはnormal / fault scenarioについて、source SHAへbindingした
`report.json`と`evidence.json` runtime artifactを生成します。

freezeは一度のephemeral CI reportをsource controlへコピーすることには依存しません。
workflow、proof contract、source anchor、required safety semanticsをversion管理し、
後続proof runは毎回自身のexact source SHAへbindingする必要があります。

## 5. Freeze後に許可するchange

既存contractとproof testを維持する限り、次はarchitecture reopenなしで許可します。

- security / correctness fix
- dependency maintenance
- observable contractを維持するconsolidation / refactoring
- evidenceに基づくdead / duplicate path削除
- test strengthening
- documentation / external-review artifact
- execution semanticsを変えないbenchmark instrumentation

許可されたchange classでも自動的に安全という意味ではありません。
CI、targeted proof check、human reviewは継続します。

## 6. Architectureをre-openするchange

次は新しいarchitecture decisionが必要です。

- fail-closedを弱める
- authorization / consumptionの意味を変える
- `EFFECT_UNKNOWN`、retry、replacement blocking semanticsを変える
- credential / network authorityを広げる
- decision / authorization / receipt lineageを変える
- frozen proof claimへ別external-effect pathを追加する
- confirmed external effectの定義を変える
- controlled CI proofをproduction validationとして扱う
- separate proofなしにTrustLog exactly-onceをこのclaimへ含める

永久禁止ではありません。Consolidationやmaintenance PRに紛れ込ませず、
明示的にarchitectureをre-openするという意味です。

## 7. Explicit non-claims

このArchitecture Freezeは次を証明しません。

- production readiness
- real customer credentials
- real customer endpoint
- independently operated production infrastructure
- external UTC clock trust
- TrustLog exactly-once publication
- regulatory approval / certification

これらは別のfuture claimであり、別のevidenceが必要です。

## 8. 次のphase

このfreezeがmergeされた後の次工程は**Large Consolidation Audit**です。

auditでは、このfrozen contractを基準として以下を評価します。

- redundant implementation
- duplicate verifier
- unused abstraction
- oversized schema
- similar test duplication
- dead path
- historical compatibility layer

frozen proofを保てる場合は、拡張より削除・単純化を優先します。
