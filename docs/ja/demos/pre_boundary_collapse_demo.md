# Pre-Boundary Collapse Demo Walkthrough

## Trajectory Shaping Lineage v0

lineage は、最終的にどの decision が bind されたかという記録だけではありません。
この demo では、bind 前に reachable decision space がどのように変形したかも lineage として記録します。

`trajectory_shaping_lineage` は、
`demo_scenario=pre_boundary_collapse` のときに `governance_layer_snapshot` 配下の
additive snapshot field として公開されます。

このフィールドは、以下の structural marker の sequence を記録します。

- exposure asymmetry emergence
- divergence contraction
- participation shift from informative/participatory to decision-shaping
- preservation degradation and intervention threshold crossing
- final bind evaluation over an already narrowed space

この sequence によって、reviewer はパターンを再利用可能な形で評価できます。
どこまで intervention が viable だったか、どこで structural loss が始まったか、
そして bind が最終的に何を評価したかを一貫して追跡できます。

Known limitation: this is a deterministic representative demo lineage and is
not production certification.


## A/B/C/D Minimal Validation Case

Pre-Boundary Collapse demo には、additive fixture として
`trajectory_shaping_lineage.abcd_minimal_validation_case` も含まれます。この case は
`A`、`B`、`C`、`D` の4 options だけを使い、option exposure、preservation、
intervention viability、bind admissibility が分離し始める最小の representative
trajectory を reviewer が確認できるようにします。

最小 A/B/C/D shape が有用なのは、過度な一般化を避けられるためです。reviewer は、
rich domain scenario や大きな option set から pattern を推論する必要がありません。
代わりに、制約された条件でも以下の governance-relevant separation が現れるかを確認できます。

- A/B reinforcement が初めて検出可能になった時点で preservation degradation が始まる
- C/D が形式上残っている間に divergence contraction が measurable になる
- bind が final trajectory を評価する前に intervention viability が失われる
- formal bind admissibility は、すでに narrowed された space に対して valid になり得る

これにより VERITAS は、bind 前に何が現実的に preservable / enactable として残っていたかを追跡できます。
bind layer は実際に評価した space に集中しつつ、trajectory lineage はその space がいつ狭まったかを示します。
この result は deterministic representative governance pattern であり、certification や production governability claim ではありません。

## Dynamic Conditions Validation v0

Dynamic Conditions Validation v0 は、A/B/C/D Minimal Validation Case の次段階となる
deterministic representative validation pattern です。minimal case は、制約された
A/B/C/D 条件のもとで preservation degradation、intervention viability loss、formal
bind admissibility が構造的に分離して観測できることを示します。dynamic case は、
bind 前に複数の trajectory-shaping pressure が相互作用しても、同じ separation が
見えるかを確認します。

additive fixture は
`trajectory_shaping_lineage.dynamic_conditions_validation_case` として公開され、
base option set は `A`、`B`、`C`、`D` のまま維持します。追加される dynamic factor は
以下です。

- reinforcement
- exposure asymmetry
- time pressure
- adaptive system behavior

5 phases は compact に保たれます。balanced option space から始まり、reinforcement と
exposure asymmetry、time pressure による intervention window compression、adaptive
behavior による narrowed trajectory の stabilization、そして dynamically narrowed
space に対する formal bind evaluation へ進みます。これにより、governability は binary
condition ではなく、formal bind admissibility が intact のままでも時間とともに劣化し得る
ことを sequence として確認できます。

この validation は dynamic pressure 下で preservation degradation、intervention viability
loss、formal bind admissibility を比較するためのものです。certification、general dynamic
trajectory engine、production governability claim ではありません。

## Irreversibility Horizon v0

Irreversibility Horizon v0 は、Dynamic Conditions Validation v0 の次に置く小さな
marker layer です。Dynamic Conditions Validation v0 は、reinforcement、exposure
asymmetry、time pressure、adaptive system behavior が相互作用しても、preservation
degradation、intervention viability loss、formal bind admissibility を分離して観測
できることを示します。Irreversibility Horizon v0 は、その上で「operational
irreversibility が安定化する前に、structurally meaningful degradation がどれだけ早く
見え始めるか」を問います。

これは production 用の irreversibility 判定エンジン、score model、または新しい enforcement
gate ではありません。
`trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon`
に追加される deterministic representative validation pattern です。既存の dynamic sequence
に対して、次の代表的な temporal points を示します。

- **first structural degradation signal** — Phase 2。reinforcement と exposure asymmetry
  により最初の dynamic asymmetry が検出可能になるが、介入はまだ現実的に可能な段階。
- **early warning** — Phase 3。time pressure により intervention window が短くなり始めるが、
  meaningful intervention はまだ可能な段階。
- **last meaningful intervention** — Phase 3。adaptive stabilization の前に、代表パターン上
  meaningful intervention が可能な最後の段階。
- **irreversibility horizon** — Phase 4。adaptive behavior が narrowed trajectory を安定化し、
  recovery が operationally hard になる段階。
- **bind after horizon** — Phase 5。representative horizon を越えた後の formally admissible
  trajectory を bind が評価する段階。

この marker は、OpenAPI、bind contract、state family、pre-bind vocabulary を変更しません。
production governability claim も行いません。目的は、bind 時点で formal admissibility と
inspectability が残っていても、その上流で meaningful intervention capacity の回復が
operationally hard になっている可能性を、代表パターンとして可視化することです。

## Actor Recognition Gap v0

Actor Recognition Gap v0 は、Irreversibility Horizon v0 の次に置く小さな marker
layer です。Irreversibility Horizon v0 が structural intervention capacity の回復が
operationally hard になる地点を示すのに対し、Actor Recognition Gap v0 は「remaining
intervention capacity の visibility が、当事者がその損失を十分に認識する前に、いつ劣化し始めたか」
を問います。

この layer は actor psychology を推定しません。actor の belief を予測せず、awareness を scoring
せず、自動 enforcement も追加しません。
`trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon.actor_recognition_gap`
に追加される additive な deterministic representative validation pattern です。OpenAPI、bind
admissibility、state family、pre-bind vocabulary は変更せず、structural degradation と reduced
intervention capacity に対する actor recognition の間に生じ得る representative visibility gap を示します。

この marker は、次の代表点を区別します。

- **actual degradation visible** — Phase 2。reinforcement と exposure asymmetry により
  structural degradation が最初に見え始める段階。
- **actor still perceives governable** — Phase 2。system が actor にはまだ formally open かつ
  procedurally coherent に見え得る段階。
- **visibility degradation** — Phase 3。time pressure が intervention window を圧縮し、remaining
  intervention capacity の visibility が劣化し始める段階。
- **recognition gap** — Phase 3。structural degradation と reduced intervention capacity に対する
  actor recognition の間に代表的な lag が生じる段階。
- **recognition alignment** — Phase 4。adaptive behavior により narrowed trajectory が安定化し、
  meaningful divergence の回復が operationally hard になった後で、actor がようやく認識し始め得る段階。
- **bind after recognition gap** — Phase 5。representative recognition gap が上流ですでに発生した後、
  formally admissible な trajectory を bind が評価する段階。

目的は visibility であり、formal assurance、prediction、production governability claim ではありません。
system は formally open、procedurally admissible、apparently governable に見え続ける一方で、meaningful
divergence capacity は上流ですでに progressively nonviable になっている可能性があります。

## Governance Attack Surface Registry v0

Governance Attack Surface Registry v0 は、Actor Recognition Gap v0 の次に置く compact
visibility layer です。Actor Recognition Gap v0 は、intervention capacity の visibility が
劣化し始めた後でも、actor には trajectory がまだ governable に見え得ることを示しました。
この registry は、その次の meta-governance の問い、つまり「governance process 自体が
attack surface にならないために、どの structural safeguard が必要か」を扱います。

この layer は complete security、certification、formal verification、production threat coverage、
automatic attack detection、automatic enforcement を主張しません。
`governance_layer_snapshot.governance_attack_surface_registry` に追加される additive な
deterministic representative visibility registry です。OpenAPI、bind contract、state family、
pre-bind vocabulary、Trajectory Shaping Lineage v0、Irreversibility Horizon v0、Actor Recognition
Gap v0 の挙動は変更しません。

registry の焦点は、governance evidence、approval、policy、escalation、replay trace が操作・偽装・
bypass・self-authorizing 化され得る代表的な governance-process failure classes を見えるようにすることです。
最初に重視する critical failure class は governance self-authorization / evidence-chain manipulation です。
問題は危険な decision が起きることだけではなく、その decision が後から safe、admissible、reviewed に
見えるよう evidence や approval path が shaping され得る点にあります。

Governance Attack Surface Registry v0 は、次の representative failure classes を含みます。

- **self_authorization** — governance または governed component が、independent governance authority
なしに自身の action を承認したように見える failure。
- **evidence_chain_manipulation** — decision を正当化する evidence が後から変更、並べ替え、欠落、
差し替えされる failure。
- **approval_receipt_spoofing** — human approval receipt / authorization proof が、reliable provenance
なしに valid に見える failure。
- **policy_snapshot_drift** — decision / bind 時点の policy snapshot が後から再現できなくなる failure。
- **escalation_suppression** — warning、pause、review、escalation が必要な条件が governance trace に
残らない failure。
- **replay_trace_tampering** — replayable audit trace が欠落、順序変更、上書きされ、observed governance
sequence を再現できなくなる failure。
- **recognition_gap_masking** — Actor Recognition Gap v0 / intervention capacity visibility markers が
governance evidence として残らない failure。

各 failure class は、separation of decision and governance authority、immutable evidence chain、policy
snapshot hashing、approval receipt provenance、replayable escalation trace、append-only governance log、
recognition gap visibility marker などの structural safeguards に対応づけられます。これは methodological
restraint を維持するための registry です。representative class と safeguard mapping を可視化しますが、
scoring model、detection engine、blocking behavior、security guarantee、certification claim にはしません。

## Governance Safeguard Coverage Matrix v0

Governance Safeguard Coverage Matrix v0 は、Governance Attack Surface Registry
v0 の次に置く compact な follow-on layer です。Registry は、governance process
自体が attack surface になり得る representative failure classes と、それを可視化する
structural safeguards を識別します。Coverage Matrix は、その関係をさらに読みやすくし、
各 failure class を primary safeguard、supporting safeguards、そして coverage を点検するための
visibility evidence に対応付けます。

この matrix が問うのは、**どの structural safeguard がどの governance attack surface を
cover し、その coverage をどの evidence が visible にするのか**です。既存 contract を壊さない
additive field として、
`governance_layer_snapshot.governance_attack_surface_registry.safeguard_coverage_matrix`
に配置されます。そのため、Trajectory Shaping Lineage v0、Dynamic Conditions Validation v0、
Irreversibility Horizon v0、Actor Recognition Gap v0、Governance Attack Surface Registry v0
の既存 consumer は、従来の field をそのまま参照できます。

v0 matrix は deterministic representative visibility model として扱います。各 row は次の関係を
明示します。

- `failure_class_id` — registry にある representative governance attack surface。
- `primary_safeguard_id` — その surface を可視化する主たる structural safeguard。
- `supporting_safeguard_ids` — review を補助する safeguard。
- `evidence_requirement` — coverage を点検するために reviewer が必要とする evidence marker。
- `visibility_question` — その row が答える review question。
- `coverage_state` — v0 では `representative_visibility_only`。
- `limitation` — row ごとに明示される non-claim。

これは methodological restraint を保つための visibility matrix です。complete prevention、
production security、scoring、automatic attack detection、automatic enforcement、formal verification、
certification は主張しません。Registry をより inspectable にする一方で、enforcement engine には
変えません。
