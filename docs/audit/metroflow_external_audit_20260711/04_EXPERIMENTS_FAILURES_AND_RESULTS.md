# Experiments, Failures, And Research Results

## Evidence Policy

Results below are separated into internal regression evidence, measured
diagnostics, and scientific validation. None of the experiments validates
real-world traffic or urban morphology. Timing values are host-, dependency-,
and workload-specific. Canonical artifacts are cited where preserved.

## 1. Deterministic Baseline And Replay

The repository previously reported `570 passed` at source baseline `96e54ca`,
with Ruff and diff checks clean. Tests cover config validation, backend
fail-closed behavior, NumPy/Rust parity, route candidates, replay, morphology,
artifacts, and optional JAX surfaces. This is strong internal regression
evidence.

It is not independent reproduction. There is no CI workflow, Python/complete
environment lock, coverage report, or second-author review in git. Rust
dependencies do have a tracked `Cargo.lock`. Optional hardware tests may skip
when their dependency/device is absent.

## 2. Integrated Runtime Self-Drive Probe

Configuration: population target 100, active capacity 100, spawn cap 100,
seed 41, eager trip generation enabled; then three `simulation_step` calls.

```text
initial: trips=16, turn_demand=0.0, queue=0.0
tick 1: active=15, moved=0, completed=0, failed=1,
        turn_demand=0.0, outflow=0.0, queue=15.0
tick 2: active=15, moved=0, completed=0, failed=0,
        turn_demand=0.0, outflow=0.0, queue=15.0
tick 3: active=15, moved=0, completed=0, failed=0,
        turn_demand=0.0, outflow=0.0, queue=15.0
```

Interpretation: trip activation and queue seeding work, but route demand is not
translated into turn demand. No turn flow/outflow budget is created and agents
stall. This falsifies the claim that the integrated runtime currently provides
a self-driving city-to-flow-to-agent loop.

## 3. Rust Routing Bakeoff

Workload: one seed, one eager step, release-built extension.

| Backend | External elapsed | Recorded runtime wall |
|---|---:|---:|
| Python/NumPy baseline | 8.02 s | 7.45797 s |
| Rust routing | 26.70 s | 26.1646 s |

Rust reduced dynamic-potential share to about 0.0193, but path-build and
metadata shares rose to about 0.4249 and 0.4977. The Python baseline potential
share was about 0.5376 for one step and 0.5094 for two steps.

Decision: reject whole-runtime Rust routing as a default. Preserve narrow
potential/cache experiments only. This is a classic case where a faster inner
kernel loses at the parent stage because data conversion and adjacent work
dominate.

## 4. Baseline Dynamic-Potential Correctness Failure

The Python reverse-Dijkstra heap comparison used values that could reject valid
float32 improvements as stale. Generated OD routes were incorrectly classified
as unreachable. After repair, the measured route-stage composition changed and
the previously selected path-build optimization ceased to be review-ready.

Decision: correctness reset accepted; prior hotspot recommendation deprecated.
This is the strongest recorded local-minimum example in the project.

## 5. Planar City Trial

Seed-44 explicit planar mode reduced 2,665 proper crossings to zero and retained
32/32 sampled OD routes. Making the mode the default increased full-suite time
from roughly 48 seconds to 281 seconds and broke a route-ID regression.

Decision: keep `standard` as default and planar construction as an explicit
sidecar gate. A topologically legal map was still visually dominated by sparse
clusters and long corridors, proving that planar legality is not morphology
realism.

## 6. Morphology Quality Gates

Continuous-fabric work reported these three-seed median local-cell-presence
changes:

| Style | Before | After |
|---|---:|---:|
| ring | 0.172 | 0.618 |
| grid | 0.309 | 0.759 |
| polycentric | 0.338 | 0.483 |
| river | 0.342 | 0.625 |
| mixed | 0.267 | 0.615 |
| organic | 0.152 | 0.491 |

Junction-proximity minima ranged from 0.421 to 0.958. A visual counterexample
showed that long lines could satisfy presence alone, so the gate added local
junction proximity. This was an appropriate Goodhart correction.

Decision: accept the metrics as synthetic regression gates. Do not claim
named-city realism, parcels/buildings, terrain realism, or observed morphology
fit.

## 7. Morphology-Gated Land-Use Accessibility

Across six styles and seeds 17, 29, and 41, both legacy and morphology placement
reported 1.0 POI access validity and directed representative-zone
reachability. Zone centers changed in every comparison and at least 99.7% of
POI access nodes changed while aggregate IDs/types/capacities were preserved.

Decision: morphology placement does not break the tested reachability
contracts. It does not authorize morphology-aware demand, estimate mode choice,
or validate trip distributions.

## 8. JAX Dense-Flow Persistent Chunk

Hardware: RTX 3080 Ti 12 GB; frozen inputs retained on device for 512 steps.

| Links | Max drift | Warm speedup minimum | Steady speedup | Gate |
|---:|---:|---:|---:|---|
| 4,096 | 0.0008612 | 1.1247x | 12.2843x | pass |
| 16,384 | 0.0008769 | 4.2620x | 37.7757x | pass |
| 65,536 | 0.0015769 | 13.5368x | 85.3313x | fail drift |

Decision: real tensor acceleration exists for the frozen chunk, but no runtime
backend is authorized. The experiment excludes per-tick host synchronization,
events, agent mutation, checkpoint ownership, and integrated replay. The
largest case’s numeric drift exceeds the fixed `1e-3` limit.

Canonical artifacts:
`artifacts/gpu_dense_flow_bakeoff_20260711/`.

## 9. Row-Local Cost-To-Go Feature Audit

Corpus: 64,968 rows from nine generated maps, multiple destinations, and free-
flow/stressed/closure states.

- 90% of features were nonconstant.
- 99.889% of matched rows changed feature and target jointly.
- relation coverage was 20.042%.
- 8,994 of 13,021 covered rows conflicted in normalized target: 69.073%.
- the fixed maximum conflict gate was 25%.

Decision: reject a row-local MLP before training. Global graph context is
missing. The threshold was fixed within the PR before the canonical run but was
not independently preregistered earlier.

Canonical artifacts:
`artifacts/cost_to_go_feature_audit_20260711/`.

## 10. Graph Tensor Contract

The NumPy graph contract preserves directed edge index, 13 edge features,
blocked mask, destination context, node target masks, byte-bounded padding, and
static-network holdout. One recorded sample/batch had 861 nodes, 3,120 edges,
1,722 targets, 534,996 final bytes, and 1,069,992 peak allocated bytes.

Decision: data contract accepted. No model accuracy or runtime speed claim
follows from tensor construction.

## 11. JAX Graph-Aware Cost-To-Go Experiment

Workload: 72 graphs, 48 train, 24 held-out-map validation, three model seeds,
30 epochs, fixed graph-aware model versus a row-local control.

| Seed result | Graph/control normalized-MAE ratio |
|---|---:|
| 1 | 1.0305 |
| 2 | 1.1823 |
| 3 | 0.9615 |
| mean | 1.0581 |

The acceptance gate was at most 0.90 and passed 0/3 seeds. Repeat maximum
prediction difference was 0.1617336 versus a `1e-4` gate; MAE difference was
0.0083477 versus `1e-5`. Graph steady inference was about 2.30-2.33 ms versus
0.106-0.123 ms for the row-local control.

Decision: formal result is inconclusive because determinism failed, while the
accuracy gate fails independently. Stop tuning this fixed hypothesis. This does
not prove graph context is useless; it rejects the tested model/configuration.

Canonical artifacts:
`artifacts/jax_graph_cost_to_go_bakeoff_20260711/`.

## 12. What Has Not Been Measured

- a functionally closed 100k-population integrated rollout;
- observed traffic counts, speeds, queues, route shares, or travel times;
- calibration/validation split against named cities;
- complete LUTI evolution in the new runtime;
- GPU flow with realistic per-tick mutation and host/device checkpoints;
- NN generalization beyond generated-map holdouts;
- energy, memory bandwidth, or long-run numerical stability;
- multi-user/independent reproduction.

These absences define the current research ceiling.
