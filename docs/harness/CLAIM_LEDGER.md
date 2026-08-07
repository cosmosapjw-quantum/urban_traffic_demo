# Claim Ledger

Status: active source of truth
Last updated: 2026-07-13

This file is the compact project-level claim authority. The external-audit
version with evidence and falsifiers is:
`docs/audit/metroflow_external_audit_20260711/06_CLAIM_PROVENANCE.md`.

## Specified Design

- `docs/TRAFFIC_SIMULATION_FINAL_MODEL_SPEC.md` consolidates the normative
  target equations for demand, conservative link/node flow, physical link
  traversal, route choice, rerouting, lagged accessibility/land-use feedback,
  and baseline-bounded EMA/bandit adaptation. It is a **SPECIFIED** design
  artifact, not evidence that every equation is implemented, calibrated, or
  empirically validated.

## Implemented

- Python 3.12 + NumPy baseline with optional Rust CPU and optional JAX extras.
- Synthetic typed road topology, connectivity repair, optional planar sidecar,
  six morphology grammars, zones, POIs, deterministic citizens/trips.
- NumPy point-queue/node flow arrays, reverse-Dijkstra routing, ranked-K
  candidates, path-size selection, event/cadence rerouting, active-agent pool.
- Explicit NumPy `spatial_queue_v1` with length/speed link residency, finite
  lane-length storage, exit-ready demand, source admission blocking, and
  deterministic downstream spillback; `point_queue_v1` remains the default.
- Exhaustive deterministic generated turn authority, route-tail per-turn/sink
  demand, fair sink/turn deficit allocation, fractional service/receiving carry,
  exact agent/queue token commit, final-link destination validation, and
  fail-closed finite/integral token metadata validation.
- Replay fingerprints bound to complete initial state, ordered controls, actual
  RNG key, and step count; per-tick queue-transition witnesses; measured
  benchmark/report surfaces; static/runtime diagnostic renderers; Rust parity
  kernels; and bounded GPU/NN experiments.
- A deterministic realistic-city plausibility audit binds the pinned reference
  corpus, mechanical 20-percent envelopes, PR53 structural gates, 30 generated
  map fingerprints, diagnostic motif/hierarchy counters, and review artifacts.
- A generator-independent morphology control table scores any
  `PreviewCityTopology` against the pinned envelope, on the OSMnx-equivalent
  simplified graph, with per-metric discriminative-power diagnostics.
- An opt-in `osm_wiki` lane-tagging policy interprets three documented OSM
  patterns - single-track two-way streets, contraflow lanes on one-way streets,
  and partially tagged directions - that the strict reader rejected as
  malformed. Measured at `1.7%` of drive-network ways across seven extracts, but
  fail-closed import made them block `6/7` cities. `strict` remains the default;
  contradictory and unparseable tags still fail closed under both policies.

## Internally Verified

- Deterministic regression and replay contracts covered by local tests.
- Explicit optional backends fail closed; `auto` alone may fallback.
- Synthetic connectivity/morphology/accessibility gates pass their recorded
  fixture matrices.
- Isolated Rust kernels match their Python/NumPy fixtures.
- JAX frozen dense-flow chunks accelerate tested 4,096/16,384-link workloads.
- The seed-41 eager self-drive probe compiles 51,886 turns, completes all 15
  routable trips by tick 16, records one explicit no-route failure, and reaches
  zero active agents/queue mass with exact per-link agent/queue equality through
  20 ticks.
- Two fresh seed-41 20-tick replays produce the same canonical final-state
  fingerprint and replay telemetry; stale residual boundaries fail before run.
- Ten deterministic 64-tick generated runs close 158 trips as 148 completions
  and 10 classified no-route failures with zero observed link-level
  agent/queue delta. A seed-41 10k-population run closes 3,105 trips at tick 156
  in the local corrected-runtime measurement.
- Optional JAX dense-flow parity is restored after aligning its point-queue
  receiving and additive-delay equations with NumPy/Rust; the measured
  4,096/16,384-link maximum drift is below `1.6e-5`.
- Accretive growth replaces the stencil family and clears the morphology gate.
  `growth_fabric_v1` grows streets step by step under local constraints instead
  of connecting a fixed point set, which produces by construction the three
  properties no stencil can reach: T-junctions from snapping onto a street
  interior, dead ends from tips that cannot legally extend, and curvature from
  per-step turning. On the calibrated instrument over the fixed 6-style x
  5-seed matrix it passes all seven empirical metrics on `29/30` maps, against
  `15/30` for `sidecar_local_fabric` and `0/30` for `realistic_synthetic_v1`.
  Measured ranges: mean node degree `3.11-3.39` (was `4.98-5.72`), dead-end
  share `0.056-0.122` (was `0.0000-0.0025`), circuity `1.009-1.013` (was
  exactly `1.0`), and per-style orientation order spanning `0.001` for
  `ring_radial` to `0.78` for `grid_core`. A companion compiler keeps each
  junction-to-junction chain as one curved centerline with arc-length links,
  which is what allows circuity above `1.0` at all.
- The repaired morphology instrument admits a real-city positive control. Five
  offline OSM extracts spanning gridiron (Chicago), planned superblock
  (Barcelona), traditional organic (Seoul), polycentric TOD (Tokyo), and
  distributed sprawl (Charlotte) all land inside the pinned envelope on every
  one of the seven metrics, with `orientation_order` spanning `0.121-0.873` and
  median segment length `52.3-122.0 m`. The envelope is therefore falsifiable
  and admits the real-world span; it is not the reason synthetic maps fail.

## Refuted Or Blocked

- At the frozen 2026-07-11 audit baseline, the integrated generated-city runtime
  was not self-driving. That result remains a historical negative control and is
  superseded only by the bounded 2026-07-12 remediation evidence above.
- Whole-runtime Rust routing is slower than baseline in the recorded eager
  smoke workload.
- The row-local cost-to-go MLP input hypothesis fails its relation-conflict gate.
- The fixed graph-aware model misses its accuracy gate and repeat determinism.
- The 65,536-link JAX dense-flow chunk exceeds the fixed drift gate.
- The PR62 plausibility instrument was uncalibrated and could not be falsified.
  Three defects are measured and now repaired:
  (a) `plausibility_audit` generated its own maps with
  `topology_mode="realistic_synthetic_v1"`, so no control arm - including the
  offline OSM importer built for this purpose in spec 039 - could ever be
  scored on it;
  (b) `morphology_metrics` counted every compiled node, while the pinned Boeing
  corpus reports OSMnx values measured after `simplify_graph` contracts
  degree-2 interstitial nodes, so node spacing rather than morphology moved
  `mean_node_degree` and `dead_end_share`;
  (c) the `[0.8*min, 1.2*max]` envelope was derived without reference to each
  metric's attainable range, putting `orientation_entropy`'s upper bound at
  `4.2984` against a theoretical maximum of `log(36) = 3.5835`, so that bound
  could never fail. `orientation_order` remains vacuous (0.998 coverage) and
  `circuity`'s lower bound remains inert at the theoretical minimum; both are
  now reported rather than silently passing.
- `realistic_synthetic_v1` regressed against a path already in the tree. On the
  repaired instrument over the fixed 6-style x 5-seed matrix,
  `sidecar_local_fabric` - which `PRD_REALISTIC_SYNTHETIC_CITY.md` froze as the
  "negative control" on the strength of a contact sheet, unmeasured - passes all
  seven empirical metrics on `15/30` maps, versus `0/30` for
  `realistic_synthetic_v1`, `0/30` for `sidecar_local_fabric_planar`, and `0/10`
  for the `standard` runtime default. The incumbent default fails
  `mean_node_degree` on every map it can generate, so gate failure carried no
  information until a control existed. Authority:
  `artifacts/runtime_spine_review/morphology-control-table-20260807.json`.
- `realistic_synthetic_v1` default promotion is blocked. The fixed 30-map PR62
  audit passes zero maps: every map is too highly connected and has too few
  dead ends relative to the pinned envelope; seven also exceed the developed
  branch-free corridor threshold. Visual inspection shows repeated triangular
  fabric and no collector-length hierarchy. PR63 independently fails 100k
  generation wall, realized population, and paired throughput on all three
  seeds, while admitting no single Rust generation stage. PR64 preserves
  `standard` and records the conjunctive decision as `BLOCKED`.

## Not Validated

- Complete 100k-population integrated runtime behavior. A bounded seed-41 run
  reaches tick 128 in 226.09 s with 10,626 vehicles still active and therefore
  does not establish closure or operational throughput.
- Real-city road morphology, traffic flow, route choice, demand, or LUTI fit.
- Broad generated/event conservation and replay across arbitrary, long-running,
  incident, merge/diverge, reroute, and failure workloads.
- Empirically calibrated link traversal, storage/jam density, spillback wave
  speed, fundamental diagram, or shockwave propagation. The explicit spatial
  queue is implemented substrate, not empirical traffic validation.
- A unified `SimulationState` traffic/accessibility/land-use feedback loop.
- Runtime JAX/GPU flow with realistic host mutation and checkpoints.
- Production neural-network inference or route authority.
- Independent artifact reproduction or redistribution under a root license.

## Forbidden

- External-data learning.
- NN, RL, or LLM as route-legality/state-mutation authority.
- Smoke/PNG/HTML artifacts presented as scientific validation.
- Silent fallback for an explicitly selected optional backend.
- Direct CSUR city-generator/compatibility claims or unlicensed source reuse.

## Promotion Rule

No backend or scientific claim may be promoted solely from parity, static atlas
classification, one smoke workload, or visual inspection. Functional closure,
deterministic invariants, a falsifiable measured probe, exact provenance, and
baseline fallback are required.
