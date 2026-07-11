# Development History

## Provenance Boundary

The audited repository contains 120 commits, one recorded author, no merge
commits, and nine local refs. The first retained commit is `0492364` on
2026-03-26, titled `import repaired bundle`, and already contains 80 files.
Nothing in the supplied git objects proves what happened before that import.
There is a 99-day gap between the March baseline work and the large July donor
absorption. Branch names are useful pointers, not independent review evidence.

## Phase 0 - Imported Vision And Constitution

Commits: `0492364`, `6524500`

The initial bundle established a 100k-scale synthetic city ambition,
persistent citizens, mesoscopic traffic, K paths, event rerouting, lagged LUTI,
replay, and design documentation. The constitution formalized deterministic
state, explicit units, multirate scheduling, and the ban on lane-level default,
RL/LLM-first routing, ECS-first architecture, and distributed multi-GPU.

Critical assessment: the documentation was more mature than the executable
model. This was useful as a contract seed but makes the first commit unsuitable
as proof of implementation completeness.

## Phase 1 - Executable Baseline

Commits: `f26a1a2` through `faf96aa` (five commits)

The first implementation added fast edge evolution, multirate orchestration,
accessibility/land-use updates, benchmark surfaces, and routing integration.
It established the legacy `WorldState` path that still contains the only
accessibility and land-use scheduler.

Critical assessment: no preserved run artifact establishes that the full
initial city model ever ran at the promised scale. The code was a coherent
small baseline, not a demonstrated 100k simulator.

## Phase 2 - Donor Absorption And Runtime Spine

Commits: `f0faf03` through `fddcaa2` (13 commits)

The donor absorption introduced city generation, NumPy flow states, dynamic
routing, demand, active agents, events, UI snapshots, metrics, replay, and an
integrated `SimulationState` step. Follow-up fixes connected movement budgets,
seeded source queues, repaired generated-network connectivity, and corrected
optional Rust fallback behavior.

Critical assessment: this is the project’s largest capability jump and largest
provenance/architecture jump. The donor’s source ancestry is not in git. More
importantly, the new runtime did not absorb the legacy accessibility/LUTI loop
and never added route-to-turn-demand production.

## Phase 3 - Routing Realism And Observability

Commits: `6af25ef` through `fc43cba` (29 commits)

This phase added conservative rerouting, ranked-K candidates, path-size
correction, sink discharge budgets, active-agent metadata, runtime timing,
replay fields, UI diagnostics, and measured benchmarks. Several commits
immediately repaired fallback metadata and timing totals.

Critical assessment: route contracts became substantially more explicit, but
observability expanded faster than end-to-end traffic behavior. The direct
runtime probe documented in this audit demonstrates that candidate selection
and agent allocation can execute while actual turn flow remains zero.

## Phase 4 - Broad Rust CPU Migration

Commits: `132bd96` through `9c7a8cc` (13 commits)

PyO3/maturin kernels were added for edge evolution, flow arrays, dynamic
potential, greedy/ranked routing, route metadata/scoring/selection, reroute
decisions, and active-agent action planning. The crate was split into focused
modules while keeping a stable Python facade. Python retained NumPy ownership;
Rust used explicit `Vec` copy boundaries.

Critical assessment: parity-first migration was disciplined, but breadth
preceded whole-runtime performance evidence. A later release bakeoff showed
explicit Rust routing at 26.70 s versus 8.02 s for the baseline one-seed,
one-step eager suite. The copy boundary and path/metadata work erased potential
kernel gains. Rust remains a useful optional laboratory, not a default.

## Phase 5 - Benchmark Productization

Commits: `e4dbfba` through `73df9f5` (18 commits)

The runtime benchmark became a suite with seed orchestration, CLI, Markdown,
JSON, HTML, bundle manifests, eager-demand controls, and reviewer-facing stage
reports. Commit `5708d56` fixed a maturin packaging configuration that shadowed
the root `metroflow` package; `5108349` fixed lost eager metadata.

Critical assessment: tooling made performance decisions inspectable, but it
also increased reporting surface and tracked artifact mass. Smoke timing was
at risk of becoming a product in itself. The later anti-drift rules were a
necessary response.

## Phase 6 - Anti-Drift And Correctness Reset

Commits: `4113d8d` through `7f485a8` (seven commits)

Timing was split into nested route and agent stages, then plugin-memory writes
were batched. Explicit self-ask, step-back, and compact CCoT guardrails were
added. A crucial baseline Dijkstra fix corrected float32 heap-staleness that had
misclassified reachable generated ODs as no-route.

Critical assessment: this phase demonstrates why optimization evidence must
follow correctness. Before the Dijkstra fix, path-build looked like the next
hot path; after the fix, the recommendation changed to potential recomputation
and cache amortization. Earlier timing interpretation was a local minimum.

## Phase 7 - Whole-Code Hardware-Fit Roadmap

Commits: `8ae196b` through `2871200` (15 commits)

An AST hardware-fit atlas classified about 1,105 symbols and linked them to a
workload matrix and decision cards. Cache pruning, dense flow probes, route
scoring probes, simulator labels, an optional surrogate surface, and zero-copy,
Rayon, and CUDA admission RFCs followed. Unsafe object-identity cache behavior
was removed.

Critical assessment: this was a productive step back. The optional “surrogate”
harness is still primarily a NumPy mean-by-rank baseline; the Torch branch does
not establish a trained neural model. Documentation must not describe it as a
validated NN backend.

## Phase 8 - Typed City Substrate

Commits: `0941d15` through `23d9cb7` (eight commits)

The city lane added source-provenance boundaries, physical centerlines, road
sections, node compilation, width-aware rendering, offline OSM XML import, and
planar acceptance gates. Direct CSUR source reuse was rejected.

Critical assessment: explicit planar mode removed 2,665 proper crossings in a
seed-44 audit and preserved sampled OD reachability, but making it default
increased the suite from roughly 48 s to 281 s and broke route-ID regression.
Topology legality did not solve visual morphology.

## Phase 9 - Morphology And Land Use

Commits: `25f0ba0` through `c02843a` (five commits)

Six deterministic styles, multi-seed structural gates, continuous fabric,
morphology-gated zoning/POIs, and accessibility overlays were added. A
presence-only gate was rejected after a visual counterexample showed that long
lines could game raster coverage.

Critical assessment: the resulting atlases are visibly more diverse, and
structural regressions are now measurable. They remain schematic, with no
parcel/building/terrain model or observed-city calibration. Access-node
reachability is necessary but not demand realism.

## Phase 10 - GPU And NN Falsification

Commits: `c82decb` through `96e54ca` (five commits)

Dense JAX flow chunks, a row-local cost-to-go feature audit, directed graph
tensors, and a fixed graph-aware JAX/Optax comparison were executed on the RTX
3080 Ti. The 4,096- and 16,384-link flow chunks passed; 65,536 links failed the
drift gate. Row-local features showed 69.07% near-duplicate target conflict.
The graph model averaged a 1.0581 graph/control error ratio, passed 0/3 seeds,
and failed repeat determinism.

Critical assessment: these are good negative experiments. They falsify the
tested row-local and fixed graph hypotheses; they do not falsify all graph
models or all GPU flow designs. Per-tick host mutation, synchronization,
checkpoint ownership, and integrated replay remain unmeasured.

## History-Level Conclusions

- The project is unusually honest about failed gates, but not all historical
  statements have immutable preregistration.
- The largest productivity events were broad imports and architecture slices,
  not externally reviewed merges.
- One author and no CI make local passing tests necessary but insufficient
  evidence of independent reproducibility.
- Decision documents first appeared late in the history and are partly
  retrospective.
- The correct next phase is functional runtime closure, not another isolated
  accelerator or visual gate.
