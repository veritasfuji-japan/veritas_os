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
