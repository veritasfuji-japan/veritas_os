# Material Change Semantics Consolidation Audit

Status: **DOCUMENTATION-ONLY / NON-ENFORCING**  
監査日: 2026-09-16  
監査対象 `main`: `adf185a8b4318a3b14f13fd5c2a67303e46133b8`  
Frozen controlled-proof anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

## 1. 目的

この監査で確認する問いは1つだけです。

> VERITASに今、新しいMaterial Change強制エンジンが必要なのか。それとも関連する意味論は、既存のHuman Approval、ExecutionIntent、Bind Context、Revalidation、Drift機構にすでに分散実装されているのか。

この監査自体は非強制です。runtime predicate、authorizationの意味、consumptionの意味、external-effect pathを追加しません。

またCompany側の現行ルールに従います。External PoC #1を妨げず、かつ実在するpartnerまたはpaid prospectがProduct実装を要求していないgapは、原則deferします。

## 2. 確認した主要surface

現行の実行コードとfrozen proof contractをsource of truthとして、以下を確認しました。

1. `veritas_os/governance/human_approval_receipt.py`
2. `veritas_os/policy/canonical_execution_intent_formation.py`
3. `veritas_os/policy/execution_intent_pre_bind_validation.py`
4. `veritas_os/policy/real_bind_context.py`
5. `veritas_os/policy/native_bind_authorization_consumption.py`
6. `veritas_os/policy/bind_artifacts.py`
7. `veritas_os/policy/bind_revalidation.py`
8. `scripts/demo/generate_evaluation_drift_detection.py`
9. Human Approval Workbenchのapproval edit invalidation path
10. `docs/en/architecture/controlled-execution-proof-architecture-freeze-v1.md`

## 3. 現在の意味論の棚卸し

### 3.1 Human Approval context binding

`HumanApprovalReceipt` はすでに以下の正確なgoverned contextを保持・照合できます。

- `request_ref`
- `ai_output_ref`
- `execution_intent_id`
- `decision_id`
- `approved_action_class`
- `policy_snapshot_id`
- `authority_evidence_id`
- `bind_context_hash`

`validate_human_approval_context_binding()` は、期待値とreceipt値が異なる場合にdeterministicにfailします。

つまり、これはすでにapproval-to-contextのanti-substitution boundaryです。新しいMaterial Change機構がこれを重複実装したり弱めたりしてはいけません。

### 3.2 ExecutionIntent exactness

Canonical ExecutionIntent formationは、完全なmapped intentを`execution_intent_id`と`execution_intent_hash`へbindします。

Pre-bind validationは、Bindへ進む前にexact intent、field mapping、source formation、required fields、lineage、hashを独立再構築・検証します。

これはintegrity/exactness boundaryであり、live stateやapproval validityの分類器ではありません。

### 3.3 Real Bind context

canonical real bind context hashは、verified source gateと以下をbindします。

- source gate review hash
- execution intent ID / hash
- adapter contract ID / hash
- endpoint identity binding digest
- credential reference digest
- credential scope binding digest

したがってendpoint、credential reference、credential scope、adapter contract、exact execution intentのすり替えは、すでにprotected context digestへ反映されます。

### 3.4 Native v2 current-context recheck

native v2 single-use consumption成功前に、current evidenceがfreshに再検証されます。

current contextはissuance時authorizationの以下と一致し続ける必要があります。

- bind context
- action-contract digest
- exact execution intent
- execution intent ID / hash
- source gate hash

不一致は`NABC_CURRENT_CONTEXT_MISMATCH`としてfail closedします。

これはすでにpre-effect stale/substituted-context rejection mechanismです。

### 3.5 Bind-time state drift / revalidation

`ExecutionIntent`は`expected_state_fingerprint`を保持します。`BindReceipt`はlive before/after fingerprint、`drift_check_result`、replay可能な`revalidation_context`を保持します。

Bind replay/revalidationは、保存されたadmissibility設定のもとでexpected stateとlive stateを比較でき、drift sensitivityやapproval/TTL freshnessも扱います。

これはruntime state driftに最も近い既存mechanismですが、あらゆるmaterial changeを説明するproduct-wide vocabularyはまだ統一されていません。

### 3.6 Evaluation Drift Detection

Evaluation Drift Detection v1はoffline / non-enforcingなreviewer/demo helperです。

policy identity、rule version、evaluator version、refusal boundary、material-context causeなどのevaluation/outcome attribution signalを分類します。

runtime admissibilityやexecutionには参加しません。そのため、別のarchitecture decisionなしにpre-effect Material Change authorityとして再利用してはいけません。

### 3.7 Human Approval Workbenchのedit invalidation

FrontendのHuman Approval Workbenchでは、approvedなUI recordのreviewer/signature/reason metadataが編集されるとapprovalをinvalidateし、そのworkflow内でre-approvalを要求します。

これは有用なUX/audit behaviorですが、backend execution-authorityのsource of truthではありません。

### 3.8 Human Approval engagement timing

`approval_basis_opened_at`は、存在する場合hash-bound reviewer evidenceです。引用された資料がapproval前にいつopen/presentされたかを示せます。

ただしevidence-onlyであり、read/understand/independent judgmentやalternatives consideredを証明せず、runtime authorization/admissibility semanticsも変更しません。

## 4. Consolidated matrix

| Change / condition | 既存の検知・binding | 現在のenforcement意味 | Reviewerへの説明力 |
|---|---|---|---|
| ExecutionIntent field substitution | intent hash + canonical pre-bind validation | fail closed | 技術証拠は強いがbusiness-level説明は限定的 |
| Action-class substitution | Human Approval binding / governance validation | fail closed | 良好 |
| Policy snapshot substitution | Human Approval binding / current governance checks | fail closed / revalidation | 良好 |
| Authority evidence substitution | Human Approval context + authority proof lineage | fail closed | 良好 |
| Endpoint identity change | bind-context digest | context mismatch / fail closed | 技術的に強いがfield-level cause未統一 |
| Credential reference change | bind-context digest | context mismatch / fail closed | 技術的に強いがfield-level cause未統一 |
| Credential scope change | bind-context digest | context mismatch / fail closed | 技術的に強いがfield-level cause未統一 |
| Adapter contract change | bind-context / action-contract digest | context mismatch / fail closed | 技術的に強いがfield-level cause未統一 |
| Live state fingerprint drift | bind admissibility / revalidation | stored ruleに従いblock/escalate | Bind evidence内では良好 |
| Approval expiry/freshness | approval validation / bind admissibility | fail closed / block or escalate | 良好 |
| Workbench approval metadata edit | frontend invalidation | UI上でre-approval要求のみ | UX evidenceは良いがbackend authorityではない |
| Post-outcome evaluator/policy drift | Evaluation Drift Detection helper | non-enforcing review signal | offline reviewでは良好 |
| business parameter変更 例 `amount 50000 -> 75000` | intent/contractにmodelされていれば通常exact intent/context hashへ反映 | mismatchでfail closed可能 | **Gap: unified field-level materiality explanationなし** |
| comparison input不明/取得不能 | mechanism依存 | requiredな場所では通常fail closed | **Gap: unified `INDETERMINATE_MATERIAL_CHANGE` vocabularyなし** |

## 5. 主結論

この監査から、frozen controlled proof pathへ2つ目のgeneric change-detection engineまたはapproval-invalidation engineを追加すべき根拠は確認できませんでした。

既存mechanismは、stale/substituted/drifted execution contextに対してすでに相当の保護を提供しています。また、それぞれlifecycle stageが異なるため単純なduplicateでもありません。

- approval contextは「人間が何を承認したか」を守る
- ExecutionIntentはexact intended action representationを守る
- bind contextはexact target / credential / adapter contextを守る
- native consumptionはcurrent contextとauthorized contextを再比較する
- bind revalidationはlive-state driftを扱う
- Evaluation Drift Detectionはpost-outcome evaluation driftを説明する

不足している中心は、**新しいauthorization primitiveではなく、reviewer-facing explanationの統一**です。

## 6. 特定されたExplanation gap

現在のsecure runtime pathは、例えば`NABC_CURRENT_CONTEXT_MISMATCH`という粗いstable reasonで正しく拒否できても、reviewerは「protected dimensionの何が変わったか」を自分で再構築する必要があります。

将来、additiveなexplanation artifactとして例えば以下を明示できます。

```json
{
  "changed_dimension": "business_parameter.amount",
  "approved_value_digest": "...",
  "current_value_digest": "...",
  "classification": "MATERIAL",
  "approval_effect": "REAPPROVAL_REQUIRED",
  "reason_code": "APPROVAL_SENSITIVE_PARAMETER_CHANGED"
}
```

ただし、このartifactはindependently verifiedなbefore/after evidenceからderiveされなければなりません。caller-declared labelをexecution authorityへ変換してはいけません。

## 7. 推奨方針

### 今やること

1. frozen controlled execution semanticsを維持する。
2. 新しいgeneric Material Change enforcement engineを追加しない。
3. real partner artifact到着時にはExternal PoC #1を即P0として維持する。
4. この監査をPoC-specific change-boundary documentationのsemantic inventoryとして使う。
5. bounded PoCでmaterial-change evidenceが必要になった場合は、先にそのaction classに対してchanged fieldとinvalidation条件を定義する。

### External evidenceに引かれた場合のみ後で検討

小さな **Material Change Explanation Boundary** は検討余地があります。ただし以下を満たすこと。

- additive / reviewer-facing
- side-effect free
- 既存verified contextとstable failure reasonからderive
- `UNCHANGED` / `MATERIAL` / `INDETERMINATE`を明示
- Authority / Human Approval / BindAuthorization / credential / execution permissionを発行できない
- 既存fail-closed decisionを弱められない

frozen authorization/consumption semanticsへcomposeする場合は、明示的なarchitecture-reopen decisionとhuman maintainer approvalを必要とします。

## 8. Product実装へ進む前のexit criteria

この監査がexplanation gapを示したという理由だけでruntime/governance実装を開始しません。最低でも以下のいずれかが必要です。

1. External PoC #1または別のreal partner artifactで、current evidenceだけでは扱えない具体的reviewer gapが確認された。
2. qualified paid-PoC workflowがfield-level change explanationまたはreapproval classificationを要求した。
3. security/correctness defectにより、既存context bindingがunauthorized material substitutionを許してしまうことが判明した。

どれも満たさない場合、documentation/runbook treatmentをdefaultとします。

## 9. Frozen-boundary statement

この監査はruntime behaviorを変更せず、新しいproduction claimも行いません。

変更しないもの:

- authorization issuance / consumption
- Human Approval admissibility
- current governance rechecks
- credential resolution
- Bind dispatch
- `EFFECT_UNKNOWN` / retry semantics
- reconciliation
- BindReceipt / Outcome semantics
- confirmed-effect semantics
- external-effect path

controlled-proof architectureは引き続きfrozenです。