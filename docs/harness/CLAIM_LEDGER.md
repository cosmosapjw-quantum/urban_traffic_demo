# Claim Ledger

Status: active source of truth
Last updated: 2026-08-07

Numeric claims in this file must be traceable to a committed artifact. Where a
claim and an artifact disagreed, the artifact was the reproducible side and the
prose was corrected — see the `growth_fabric_v1` entry under Internally
Verified, which previously carried four ranges that reproduced nothing.

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
  `PreviewCityTopology` against the pinned envelope under an explicitly named
  `MeasurementSpec`, with per-metric discriminative-power diagnostics. The
  default `BOEING_2019_HO` is checked against a pinned `osmnx==2.1.1` rather
  than asserted to match it: this entry previously claimed an
  "OSMnx-equivalent simplified graph" while the code implemented a hybrid that
  matched neither of Boeing's published statistics.
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
- `growth_fabric_v1` scores `30/30` on the seven empirical metrics over the
  fixed 6-style x 5-seed matrix, against `15/30` for `sidecar_local_fabric`,
  `0/30` for `realistic_synthetic_v1` and `0/10` for the runtime default.
  Measured ranges, read directly from the current authority
  `artifacts/runtime_spine_review/morphology-control-table-v2-20260807.json`:
  mean node degree `2.8603-3.2601`, dead-end share `0.1073-0.2299`, circuity
  `1.0165-1.0211`, orientation order `0.0028-0.6761`. The first three are
  unchanged from the superseded v1 artifact; orientation order moved with the
  bearing fix, and this entry previously quoted its v1 value (`0.0024-0.6463`)
  after the re-scoring had already superseded it.

  **This entry previously recorded `29/30` and four ranges that reproduce
  nothing in the tree** (`3.11-3.39`, `0.056-0.122`, `1.009-1.013`,
  `0.001-0.78`). They match neither the simplified path the artifact uses nor
  the unsimplified path `plausibility_audit` uses. The artifact was the
  reproducible side at the time: head then re-measured all 210 of its values to
  within `1e-9`. That reproduction no longer holds, and cannot: the instrument
  has since been repaired, so v1 is a historical record and v2 is the authority.
  The prose was written after the generator was rewritten, without regenerating
  the artifact it claimed to summarize.

  **What this score does not establish.** The seven metrics accept the same
  network with and without 24.4% of its edges: 97.98% of 3117 branch anchors
  lie >0.5 m from any vertex of their own parent, so re-inserting them takes
  weak components `40 -> 1` and mean degree `2.665 -> 3.525` while the envelope
  admits both. The claim that growth yields "T-junctions by construction" is
  refuted at the origin: a branch begins on its parent's interior and is not
  connected to it. `GrownNetwork.dead_end_count` is always `0`, and
  `may_dead_end` is never read inside `grow()` -- its only effect is two fewer
  steps, with the polarity inverted relative to its name. Curvature is real.
- The morphology instrument admits five offline OSM extracts on all seven
  metrics (`orientation_order` `0.114-0.938` in the current v2 artifact --
  `0.121-0.873` was the superseded v1 figure and was left here after the
  re-scoring -- median segment length `52.3-122.0 m`), so the envelope is
  falsifiable in the weak sense that real
  data can be measured against it.

  **This is not the independent positive control it was presented as.**
  (a) The same five extracts were used to calibrate `GrowthConfig.spacing_scale`,
  so they are a development set, not a holdout. (b) They are 5-12 km2 core
  bounding boxes; the pinned Boeing corpus measured whole municipalities. Three
  of the corpus's eight cities have a committed extract, and they disagree
  unevenly: measured under `BOEING_2019_HO`, Charlotte `orientation_order` is
  `0.002` in the corpus against `0.167` on our extract and Seoul `0.009` against
  `0.412`, while **Chicago agrees closely at `0.899` against `0.938`**. A core
  bbox resembles its municipality when the city is a uniform grid and stops
  resembling it when the city is sprawling or organic, so the gap is a property
  of the morphology sampled rather than an offset that could be corrected for.
  Envelope and control were never the same population. (Earlier text here said
  "two ... and both disagree" and quoted the superseded v1 figures `0.1494` and
  `0.3898`.) (c) The scores are measured through instrument defects that
  are live on this data: parallel edges between one node pair were silently
  contracted (charlotte 5, seoul 4, chicago 2, tokyo 2 pairs), which is fixed
  under `BOEING_2019_HO`. The circuity figures previously quoted here
  (`1.0324 -> 1.0255`, `1.0380 -> 1.0365`) do NOT reproduce: v1 and v2 carry
  bit-identical circuity for both cities, because self-loop length belongs in
  the numerator under Boeing's definition and the repair deliberately preserves
  that. (d) Under the importer's shipped default policy
  (`strict`), 6 of the 7 fetched extracts fail to import at all; the `5/5`
  figure holds only under the opt-in `osm_wiki` policy.

## Refuted Or Blocked

- **The generator was repaired, and the metric/consistency inversion is gone.**
  Re-scored into
  `artifacts/runtime_spine_review/morphology-control-table-v3-20260808.*`:
  `growth_fabric_v1` passes all seven metrics on 30/30 maps AND carries 1-17
  proper crossings and 2-30 unregistered touches, against 5333-12474 and
  5137-8412 before. It is now the only synthetic arm that is both.

  Measured over 6 styles x 3 seeds on the repaired generator: density
  `8.06-11.24 km/km2` against a real `7.44-17.77` (18/18 inside), dead-end share
  `0.152-0.258` against a real maximum of `0.288` (18/18 under), mean node
  degree `2.830-3.097` against a real `2.55-3.55`, local duplication
  `0.068-0.082` against a `0.15` threshold. The strict xfail asserting no
  setting could reach density, dead ends and duplication together is retired as
  refuted.

  **What this still does not establish.** `spacing_scale = 3.0` was calibrated
  against the pipeline while its spacing units were inconsistent, so that
  constant carries no authority now and has not been re-derived. Density sits in
  the lower half of the real band and the rendered fabric looks thinner than the
  extracts; nothing yet measures block-size distribution, which is what would
  distinguish correct calibration from under-seeding. One isolated 330 m
  expressway stub survives on `polycentric_tod`/17 (2 nodes of 2032), reported
  via `largest_component_share` and `isolated_fragment_sizes`. No traffic
  quantity has been measured on any of this.
- **Repairing the morphology instrument moved 392 of 945 metric values (41.5%)
  and changed no verdict.** 553 values are bit-identical between the v1 and v2
  artifacts. The member-edge bearing fix moved `orientation_entropy` and
  `orientation_order` on all 135 scores; the parallel-edge contraction fix moved
  the other five metrics on 11-29 cases each, being inert wherever those shapes
  do not occur. An earlier version of this entry claimed *every* value moved,
  which the two committed tables refute.

  The zero-chord circuity item is **not** in that list of fixes, because it
  turned out not to be a defect: OSMnx's own `circuity_avg` adds self-loop
  length to the numerator against a zero chord, so the repair preserves that and
  changes only the degenerate case where the denominator is zero, which now
  raises instead of returning 4e14. The draft design had called the lollipop's
  circuity of 5.0 a bug; the oracle shows OSMnx computes 4.99 for the same graph.

  Re-scored under `MeasurementSpec.BOEING_2019_HO` with parity checked against a
  pinned `osmnx==2.1.1`:
  `standard` 0/10, `sidecar_local_fabric` 15/30, `sidecar_local_fabric_planar`
  0/30, `realistic_synthetic_v1` 0/30, `growth_fabric_v1` 30/30, `osm` 5/5 —
  identical to the pre-repair table
  (`artifacts/runtime_spine_review/morphology-control-table-v2-20260807.*`).

  Two things follow, and the second matters more than the first. The instrument
  defects were real but were not what produced the favourable result for
  `growth_fabric_v1`. And a gate whose verdicts survive that much change to its
  own definitions is not discriminating: the same seven metrics accept a network
  with and without 24.4% of its edges.

  The geometry-vs-topology diagnostics show the inversion directly.
  `realistic_synthetic_v1`, which fails all seven metrics on 30/30 maps, is the
  only synthetic arm that is geometrically consistent — 0 proper crossings and 0
  unregistered touches, matching all five real extracts.
  `growth_fabric_v1`, which passes all seven on 30/30, carries 5333–12474
  crossings and 5137–8412 touches. The runtime default `standard` is worst at
  13957–15614. **Passing the seven metrics is at present anti-correlated with
  being a consistent graph.**
- **The morphology instrument is not fit to authorize a runtime promotion, and
  the claim that it is "OSMnx-equivalent" is unsupported.** Measured
  2026-08-07 against head `367f25d`, after an external adversarial audit:
  (a) the orientation histogram takes one unweighted bearing per member edge
  while circuity takes the contracted chain's chord — a hybrid matching neither
  Boeing $H_o$ nor $H_w$, and no code path reads an interior polyline vertex
  for a bearing, so $H_w$ is not computable here at all;
  (b) the metric is representation-dependent: the same V-shaped road returns
  entropy `ln 2` stored as one polyline and `ln 4` stored as two edges;
  (c) zero-chord segments add arc length to the circuity numerator and nothing
  to the denominator — a bare ring scores `4e14`, a lollipop `5.0`, and the
  defect is live on the OSM extracts;
  (d) parallel edges between one node pair are contracted into a closed loop,
  live on 4 of 5 extracts;
  (e) bearings are undirected, so the entropy floor is `ln 2`, not the `0`
  declared in `_THEORETICAL_RANGES`;
  (f) `orientation_order` is a pure function of `orientation_entropy`
  (bit-exact on 165/165 stored pairs, and self-consistent in Boeing's own
  published table), so the "seven metric" gate has at most six independent
  dimensions and one was counted twice;
  (g) two live measurement paths disagree — the simplify flag flips 8 of 30
  verdicts on the growth arm (30/30 vs 22/30).
  No generator may be promoted on this instrument until these are repaired and
  every arm is re-scored.
- **The seven metrics cannot detect a disconnected network.** 97.98% of 3117
  branch anchors lie >0.5 m from any vertex of their own parent, because
  `_branch_pass` interpolates the anchor and never inserts it, while
  `compile_grown_network` derives junctions only from 1 m-rounded shared
  vertices. Re-inserting the anchors takes weak components `40 -> 1` and mean
  degree `2.665 -> 3.525`, adding 3058 undirected edges — 24.4% of the correct
  edge set — and the envelope accepts the network in both states. Related
  compiler losses: a second street between one node pair is silently dropped
  (10 chains / 0.65 km on `grid_core`/17) and rings are dropped entirely.
  Reported diagnostics now exist: `grid_core`/17 scores 6909 proper crossings
  and 6261 unregistered touches, against **0 and 0 on all five OSM extracts**.
- **`artifacts/runtime_spine_review/morphology-control-table-20260807.json`
  cannot be reproduced at the commit that introduced it.** It landed in
  `c00c9e9`, whose runner imports `metroflow.city.growth_fabric` — a module
  first added in the following commit, `dae8b66`. The artifact scores an arm
  whose code did not yet exist in its own tree. This came from rebuilding the
  branch history into thematic commits without checking that each one stands
  alone. History is not being rewritten (an external auditor has already
  fetched this branch); the artifact will be regenerated at head with full
  provenance — commit, config hash, scorer source hash, fixture hashes, and the
  seed/style matrix, none of which it currently records.
- **`river_constrained` maps are severed by their river** with 0 links across
  it (53 weak components, banks of 2789 and 2382 nodes, giant-component share
  0.52). `RoadClass.RAMP` and `RoadClass.BRIDGE` exist but `growth_fabric`
  emits neither and `compile_grown_network` would raise `KeyError` on one. The
  morphology gate scored these maps without noticing.
- **The bypass does not exist as a function.** The 8 tangential expressways
  form a forest (cyclomatic number 0, 51.7% angular coverage), and the test
  that claims otherwise is satisfied by any single expressway 1200 m from the
  core — in practice by a gateway radial, not a bypass arc, whose maximum
  clearance is exactly its 2100 m seeding radius.
- **`morphology_quality`'s gate rejects 5 of its own 5 real-city controls.**
  Charlotte fails `street_density_km_per_km2 >= 10` at 7.439; all five fail
  `weak_component_count == 1`; four of five fail `block_continuity`; Chicago
  fails both cell-presence thresholds. The gate also has no density *ceiling*,
  which is why a 1.8x overshoot was invisible to the entire suite.
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

## Environment

- The NumPy path is authoritative and city generation touches no accelerator.
  Verified by generating a 7,108-node map and asserting that no `jax`, `torch`,
  `cupy` or `_metroflow_rust` module was imported: `src/metroflow/city/` contains
  zero references to any of them. JAX appears only in `traffic/meso.py`,
  `backends/jax_flow.py` and two benchmark modules; the ten Rust kernels are
  called only from `routing/`, `flow/`, `traffic/`, `sim/` and `benchmarks/`.
  The accelerator axis is auxiliary by construction, not by convention.
- Measured 2026-08-07 on an RTX 3080 Ti (12,288 MiB, driver 595.71.05,
  CUDA 13.2, nvcc 13.3): `jax==0.10.2` with `jax-cuda13-plugin` initializes
  `CudaDevice(id=0)` and executes real work. Its `float32` working precision
  matches `flow/engine.py`, so the recorded 65,536-link drift is accumulation,
  not a dtype mismatch.
- PyTorch **is** installed: `torch 2.13.0+cu130`, executing on the device
  (`torch.cuda.is_available()` is True unmasked). An earlier version of this
  bullet said it was absent, which was true when written and false by the next
  commit. Only `learning/surrogate.py` imports it, lazily, so the surrogate path
  is now reachable but still not exercised by any test that asserts on its
  numerical behaviour.

  The first install attempt failed with `[Errno 28] No space left on device` and
  left a truncated `libtorch_python.so` that raised SIGBUS on import, after
  downgrading ten of JAX's CUDA packages (cublas 13.6->13.1, cudnn 9.24->9.20,
  nccl 2.30->2.29). JAX kept working, but both frameworks now share one set of
  `nvidia-*` packages in this venv, so any future install touching either can
  move the other's dependencies.
- `pytest` used to reserve 9,194 MiB of VRAM for an entire run -- JAX
  preallocates 75% of the card the first time a device initializes, and a few
  tests exercise the optional JAX backend. `tests/conftest.py` now sets three
  defaults: `JAX_PLATFORMS=cpu` (no device is created at all),
  `XLA_PYTHON_CLIENT_PREALLOCATE=false` (bounds the damage if one is), and
  `CUDA_VISIBLE_DEVICES=""` (hides it from torch and anything added later, since
  neither reads JAX's variables). None changes dtypes, ordering or results.

  Only values conftest itself set are ever removed, and only under `--run-gpu`;
  an explicit export by the caller survives. The device mask is skipped when the
  caller has pinned `JAX_PLATFORMS` to a non-cpu platform, because masking every
  device from a JAX told to use CUDA yields `CUDA_ERROR_NO_DEVICE` rather than a
  fail-closed backend error.
