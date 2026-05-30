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
