# Metroflow Realistic City Plausibility Audit

> DIAGNOSTIC ONLY: broad synthetic plausibility audit; not named-city validation.

- report fingerprint: `6ab9f8c9c62f36aeedffd67707f2c3e9072274ca91f1e836dc14d69fcde3316b`
- maps: `30`
- passed maps: `0`
- overall: `FAIL-CLOSED`
- raw OSM included: `false`
- external-data learning: `false`

## Fixed Empirical Envelopes

| metric | reference min | reference max | accepted lower | accepted upper |
|---|---:|---:|---:|---:|
| orientation_order | 0.002 | 0.899 | 0.0016 | 1 |
| orientation_entropy | 2.083 | 3.582 | 1.6664 | 4.2984 |
| median_segment_length_m | 53.5 | 117.2 | 42.8 | 140.64 |
| circuity | 1.011 | 1.137 | 1 | 1.3644 |
| mean_node_degree | 2.546 | 3.548 | 2.0368 | 4.2576 |
| dead_end_share | 0.027 | 0.288 | 0.0216 | 0.3456 |
| four_way_share | 0.139 | 0.576 | 0.1112 | 0.6912 |

## Style Results

| style | maps passed | empirical failures | structural failures |
|---|---:|---:|---:|
| ring_radial | 0/5 | 10 | 3 |
| grid_core | 0/5 | 10 | 4 |
| polycentric_tod | 0/5 | 10 | 0 |
| river_constrained | 0/5 | 10 | 0 |
| superblock_mixed | 0/5 | 10 | 0 |
| organic | 0/5 | 10 | 0 |

## Diagnostic Counterevidence

These fields are not admission gates. They expose repeated motifs and hierarchy imbalance for review.

| style | dominant 10m length bin | dominant 2500m2 block bin | local length share | collector length share | max branch-free corridor m |
|---|---:|---:|---:|---:|---:|
| ring_radial | 0.568 | 0.861 | 0.958 | 0.000 | 887.8 |
| grid_core | 0.558 | 0.915 | 0.966 | 0.000 | 1245.8 |
| polycentric_tod | 0.630 | 0.829 | 0.973 | 0.000 | 392.7 |
| river_constrained | 0.434 | 0.748 | 0.963 | 0.000 | 517.6 |
| superblock_mixed | 0.595 | 0.936 | 0.975 | 0.000 | 392.7 |
| organic | 0.556 | 0.856 | 0.967 | 0.000 | 644.4 |

## Failed Maps

| style | seed | empirical | structural |
|---|---:|---|---|
| ring_radial | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| ring_radial | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| ring_radial | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| ring_radial | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| ring_radial | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| grid_core | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| grid_core | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| grid_core | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| grid_core | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | maximum_branch_free_corridor_m_above_800 |
| grid_core | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| polycentric_tod | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| polycentric_tod | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| polycentric_tod | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| polycentric_tod | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| polycentric_tod | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| river_constrained | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| river_constrained | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| river_constrained | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| river_constrained | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| river_constrained | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| superblock_mixed | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| superblock_mixed | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| superblock_mixed | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| superblock_mixed | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| superblock_mixed | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| organic | 17 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| organic | 29 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| organic | 41 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| organic | 44 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |
| organic | 53 | dead_end_share_outside_empirical_envelope, mean_node_degree_outside_empirical_envelope | - |

## Measurement Limits

- Circuity is measured on compiled straight fragments and is therefore 1.0 by construction in the current compiler; it is not evidence of realistic street curvature.
- The pinned eight-city corpus defines a broad envelope, not a representative global-city sample or named-city calibration.
- Motif, hierarchy, terrain, and land-use counters are diagnostic and do not introduce new admission thresholds.

## Compact CCoT

- Question: do all fixed maps satisfy empirical and structural gates?
- Evidence: per-map metrics plus diagnostic motif and hierarchy counters.
- Inference: aggregate averages cannot override any failed map.
- Counterevidence checked: repeated motifs, hierarchy imbalance, block repetition, and single-seed success.
- Decision: `fail_closed`.
- Falsifier: any failure in the fixed matrix.
- Next action: run PR63 scale evidence without changing these thresholds.
