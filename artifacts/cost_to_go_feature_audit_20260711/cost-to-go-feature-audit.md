# Cost-To-Go Feature Audit

Diagnostic only. This does not validate an NN or authorize a runtime backend.

- Maps: 9
- Rows: 64968
- Dynamic states: 18
- Canonical gate profile: true
- Threshold provenance: fixed in PR49 before the canonical run; not prior preregistration
- Nonconstant feature share: 0.900
- All state rows retained: true
- Near-duplicate relation coverage: 0.200
- Near-duplicate target conflict share: 0.691
- Cross-map holdout feasible: true
- Decision state: relation_rejected
- Row-local MLP probe authorized: false
- Runtime NN backend authorized: false

| Feature | Min | Max | Std | Nonzero share | Near constant |
|---|---:|---:|---:|---:|:---:|
| relative_x_by_spatial_diagonal | -0.756612 | 0.787518 | 0.367024 | 0.995 | no |
| relative_y_by_spatial_diagonal | -0.672673 | 0.691356 | 0.312222 | 0.995 | no |
| euclidean_distance_by_spatial_diagonal | 0 | 1 | 0.168032 | 0.999 | no |
| node_in_degree_by_max | 0.0714286 | 1 | 0.160187 | 1.000 | no |
| node_out_degree_by_max | 0.0714286 | 1 | 0.160187 | 1.000 | no |
| destination_in_degree_by_max | 0.0714286 | 0.5 | 0.112478 | 1.000 | no |
| destination_out_degree_by_max | 0.0714286 | 0.5 | 0.112478 | 1.000 | no |
| usable_outgoing_travel_time_min_by_max | 1.71115e-05 | 0.958788 | 0.148553 | 1.000 | no |
| usable_outgoing_travel_time_mean_by_max | 3.26291e-05 | 0.978103 | 0.169172 | 1.000 | no |
| usable_incoming_travel_time_mean_by_max | 0.000131727 | 0.969697 | 0.169303 | 1.000 | no |
| outgoing_effective_capacity_sum_by_max | 0.0482866 | 1 | 0.146238 | 1.000 | no |
| incoming_effective_capacity_sum_by_max | 0.0482866 | 1 | 0.146584 | 1.000 | no |
| outgoing_blocked_link_fraction | 0 | 0.666667 | 0.0662505 | 0.050 | no |
| incoming_blocked_link_fraction | 0 | 0.75 | 0.0690386 | 0.051 | no |
| global_max_travel_time_by_one_tick | 32.0104 | 78.1541 | 16.79 | 1.000 | no |
| global_mean_travel_time_by_max | 0.0480761 | 0.21841 | 0.0651851 | 1.000 | no |
| global_blocked_link_fraction | 0 | 0.0302758 | 0.0151002 | 0.500 | no |
| has_usable_outgoing | 1 | 1 | 0 | 1.000 | yes |
| has_usable_incoming | 1 | 1 | 0 | 1.000 | yes |
| is_destination | 0 | 1 | 0.0332718 | 0.001 | no |

## Compact CCoT

Question: Is row-local cost-to-go v1 ready for a bounded GPU model probe?
Evidence: Multi-style, multi-seed, two-state feature support, target relation conflicts, row retention, and a deterministic seed holdout.
Inference: Relation-sensitive support can authorize an experiment, not model adequacy.
Counterevidence checked: No fit, accuracy, replay, or runtime inference was measured.
Decision: Require PR50 adjacency/edge tensors before any model probe.
Falsifier: A leakage-safe graph contract cannot preserve directed topology and dynamic edge state within deterministic memory-bounded batches.
Next action: PR50 freezes the graph data contract; baseline Dijkstra remains authoritative.
