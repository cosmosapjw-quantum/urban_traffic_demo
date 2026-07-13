# Realistic Synthetic City Scale Gate

- Claim status: `diagnostic_scale_gate`
- Report fingerprint: `149571c18552e5cc655a0c33844fe487a7b6165cea808b1c55a3b47655f5278e`
- Populations: `1000, 10000, 100000`
- Seeds: `17, 29, 41`
- Fixed runtime ticks: `20`
- Performance gate: `FAIL`
- Prior PR62 plausibility gate: `failed_pr62`
- Default promotion eligible: `false`

This artifact is a host-local diagnostic. Performance cannot override the
independent PR62 morphology/plausibility failure.

## 100k Performance Pairs

| Seed | Generation ratio | RSS ratio | 20-tick ratio | Legacy budget ticks | Realistic budget ticks | Citizens L/R | Trips L/R | Pass |
|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|
| 17 | 2.553 | 0.859 | 1.096 | 20 | 16 | 62500/61993 | 31385/31130 | FAIL |
| 29 | 2.582 | 0.867 | 1.081 | 21 | 17 | 62500/61655 | 31210/30799 | FAIL |
| 41 | 2.770 | 0.850 | 1.101 | 21 | 16 | 62500/62604 | 31069/31115 | FAIL |

Thresholds: generation <=2.0x, peak RSS <=1.5x, parent runtime
<=1.25x, and realistic paired-budget tick count >= legacy.

## Realistic Generation Stage Shares

| Stage | Minimum | Mean | Maximum | Rust probe gate |
|---|---:|---:|---:|:---:|
| `terrain_field` | 0.000 | 0.000 | 0.000 | CLOSED |
| `urban_form_field` | 0.000 | 0.000 | 0.000 | CLOSED |
| `hierarchical_street_skeleton` | 0.036 | 0.040 | 0.043 | CLOSED |
| `continuous_local_fabric` | 0.251 | 0.267 | 0.276 | CLOSED |
| `planar_blocks` | 0.244 | 0.263 | 0.276 | CLOSED |
| `block_land_use` | 0.045 | 0.047 | 0.049 | CLOSED |
| `runtime_topology_compile` | 0.202 | 0.212 | 0.222 | CLOSED |
| `runtime_zoning_compile` | 0.008 | 0.008 | 0.008 | CLOSED |
| `quality_evaluation` | 0.131 | 0.133 | 0.134 | CLOSED |
| `unattributed_pipeline_overhead` | 0.027 | 0.029 | 0.030 | CLOSED |

Rust generation probe admitted: `false`
Candidate stage: `none`

A stage must be one of the A*/planarization/face-extraction groups and
reach at least 30 percent of city-authority time on every fixed seed.
PR63 records admission only and adds no Rust implementation.

`unattributed_pipeline_overhead` contains blueprint construction, CSR
assembly/validation, final generated-map assembly, and wrapper overhead.
It is visible counterevidence and is never Rust-admission eligible.

## City-Authority Runs

| Population | Seed | Mode | Scenario | Style | City ms | Peak RSS MiB | Nodes | Links |
|---:|---:|---|---|---|---:|---:|---:|---:|
| 1000 | 17 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 5765.997 | 151.41 | 1974 | 11280 |
| 1000 | 17 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1263.488 | 96.04 | 1141 | 5646 |
| 1000 | 29 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 6243.636 | 152.25 | 2039 | 11474 |
| 1000 | 29 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1176.134 | 96.38 | 1141 | 5646 |
| 1000 | 41 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 5638.581 | 143.69 | 1972 | 10374 |
| 1000 | 41 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1211.621 | 97.34 | 1141 | 5646 |
| 10000 | 17 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 5757.640 | 150.91 | 1974 | 11280 |
| 10000 | 17 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1229.609 | 96.28 | 1141 | 5646 |
| 10000 | 29 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 6518.130 | 150.66 | 2039 | 11474 |
| 10000 | 29 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1202.047 | 96.01 | 1141 | 5646 |
| 10000 | 41 | `realistic_synthetic_v1` | `synthetic_smoke` | `polycentric_tod` | 5753.576 | 143.24 | 1972 | 10374 |
| 10000 | 41 | `standard` | `synthetic_smoke` | `polycentric_tod` | 1169.345 | 96.44 | 1141 | 5646 |
| 100000 | 17 | `realistic_synthetic_v1` | `synthetic_100k` | `ring_radial` | 3171.300 | 82.88 | 1150 | 6128 |
| 100000 | 17 | `standard` | `synthetic_100k` | `ring_radial` | 1242.331 | 96.46 | 1128 | 5642 |
| 100000 | 29 | `realistic_synthetic_v1` | `synthetic_100k` | `ring_radial` | 3040.481 | 82.88 | 1143 | 6130 |
| 100000 | 29 | `standard` | `synthetic_100k` | `ring_radial` | 1177.610 | 95.65 | 1128 | 5642 |
| 100000 | 41 | `realistic_synthetic_v1` | `synthetic_100k` | `ring_radial` | 3215.793 | 82.61 | 1151 | 6186 |
| 100000 | 41 | `standard` | `synthetic_100k` | `ring_radial` | 1160.960 | 97.21 | 1128 | 5642 |

The 1k and 10k rows both use `synthetic_smoke`; 100k switches to
`synthetic_100k`. This is two map extents plus three population/init
workloads, not a continuous three-size city-generation curve.

## Fixed-Step Runs

| Population | Seed | Mode | Scenario/style | Init ms | Runtime ms | Init RSS MiB | Citizens | Trips |
|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1000 | 17 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 5905.922 | 8600.863 | 149.96 | 1000 | 474 |
| 1000 | 17 | `standard` | `synthetic_smoke/polycentric_tod` | 1187.970 | 512.500 | 96.69 | 310 | 148 |
| 1000 | 29 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 6457.580 | 9448.225 | 151.54 | 1000 | 536 |
| 1000 | 29 | `standard` | `synthetic_smoke/polycentric_tod` | 1223.000 | 552.015 | 96.45 | 310 | 175 |
| 1000 | 41 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 5696.514 | 9057.346 | 143.54 | 1000 | 502 |
| 1000 | 41 | `standard` | `synthetic_smoke/polycentric_tod` | 1272.020 | 545.536 | 96.60 | 310 | 147 |
| 10000 | 17 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 5813.570 | 34019.858 | 151.43 | 10000 | 4993 |
| 10000 | 17 | `standard` | `synthetic_smoke/polycentric_tod` | 1221.173 | 4673.264 | 96.48 | 6250 | 3078 |
| 10000 | 29 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 6438.077 | 35793.887 | 150.54 | 10000 | 4996 |
| 10000 | 29 | `standard` | `synthetic_smoke/polycentric_tod` | 1220.775 | 4783.030 | 97.07 | 6250 | 3134 |
| 10000 | 41 | `realistic_synthetic_v1` | `synthetic_smoke/polycentric_tod` | 5591.915 | 34264.210 | 143.82 | 10000 | 4974 |
| 10000 | 41 | `standard` | `synthetic_smoke/polycentric_tod` | 1297.283 | 4624.841 | 96.98 | 6250 | 3105 |
| 100000 | 17 | `realistic_synthetic_v1` | `synthetic_100k/ring_radial` | 3460.413 | 52642.047 | 101.14 | 61993 | 31130 |
| 100000 | 17 | `standard` | `synthetic_100k/ring_radial` | 1515.426 | 48019.089 | 101.71 | 62500 | 31385 |
| 100000 | 29 | `realistic_synthetic_v1` | `synthetic_100k/ring_radial` | 3369.776 | 52195.718 | 100.75 | 61655 | 30799 |
| 100000 | 29 | `standard` | `synthetic_100k/ring_radial` | 1425.437 | 48285.190 | 101.98 | 62500 | 31210 |
| 100000 | 41 | `realistic_synthetic_v1` | `synthetic_100k/ring_radial` | 3786.427 | 53763.860 | 100.82 | 62604 | 31115 |
| 100000 | 41 | `standard` | `synthetic_100k/ring_radial` | 1510.952 | 48844.115 | 101.98 | 62500 | 31069 |

## Compact CCoT

Question: Does scale evidence authorize promotion or one narrow generation-core probe?

Evidence: Fresh subprocess runs compare paired legacy and realistic workloads at 3 population target(s) and 3 seed(s).

Inference: The performance and Rust-admission booleans above follow fixed thresholds; they do not assess morphology.

Counterevidence checked: cumulative RSS, seed mismatch, unpaired wall budgets, nested-stage denominator drift, empty routing workload, and PR62 gate status.

Decision: Default promotion requires both performance and independent plausibility; a Rust follow-up requires the all-seed stage-share gate.

Falsifier: Any worker not isolated, any workload mismatch, any threshold change after observation, or use of this smoke artifact as empirical validation.

Next action: PR64 consumes this report together with PR62 and either promotes or records BLOCKED without changing the default.

## Visual Dependency

No generator code changed in PR63. The PR62 five-layer contact sheet is
reused as diagnostic-only visual evidence and is not validation.
