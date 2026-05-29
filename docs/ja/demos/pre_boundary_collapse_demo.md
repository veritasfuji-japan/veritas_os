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
