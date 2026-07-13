# Project State

Last updated: 2026-07-13

## Runtime Baseline

Facts:

- Host baseline is Python 3.12 on Ubuntu 24.04.
- Default runtime authority is Python/NumPy deterministic baseline.
- Rust CPU backend is optional and explicit/fail-closed.
- JAX CUDA 13 remains optional for RTX 3080 Ti 12GB experiments.
- Whole-code hardware-fit atlas is the current step-back artifact for choosing
  Rust CPU, NumPy/SIMD, JAX/GPU, NN surrogate, or keep-Python lanes.
- `docs/PRD_ACCELERATED_RUNTIME.md` and
  `docs/harness/ACCELERATION_PR_LIST.md` are the active long-term roadmap for
  spec-driven/subagent-driven acceleration work.
- PR01 (`31064c5`), PR02 (`b434258`), PR03 (`e292685`), PR04 (`a80b369`),
  PR05 (`987cdbc`), PR06 (`c2c052f`), and PR07 (`b636b2a`) are complete.
- PR08 (`29daebe`) is complete.
- PR09 (`52e7aec`) and PR10 (`04554ca`) are complete.
- PR11 (`55af343`) and PR12 are complete. The acceleration roadmap state is
  consolidated without authorizing C++/CUDA, libtorch, CMake, Rayon, zero-copy
  NumPy FFI, or new runtime backend values.

## Acceleration Evidence

Canonical evidence artifact:

- `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`

Do not copy benchmark tables into other docs unless the values are needed for a
specific decision. Link to the canonical evidence artifact instead.

## Current Accepted Direction

Derived conclusions:

- `active_agent_pool_write` was reduced below the review gate by batching
  plugin-memory replacement.
- `active_agent_pool_array_write` remains below the review gate and should stay
  a watchlist item.
- `active_agent_candidate_selection` is not currently the hot path.
- Route candidate refresh was the dominant review-ready parent stage in the
  earlier small eager suite. Post-closure scale evidence moves the current
  blocker to 100k first-tick allocation/orchestration and cadence rerouting.
- `route_candidate_potential` and `dynamic_potential_recompute` remain relevant
  inside cadence rerouting after fixing baseline Dijkstra `float32`
  heap-staleness, but their next probe must reduce the 100k parent-stage wall
  time rather than only a nested metric.
- `route_candidate_path_build` is no longer review-ready after the baseline
  correctness fix.
- Explicit whole-runtime `routing_backend="rust_cpu"` is slower than baseline
  for the 1-seed/1-step eager suite even with a release Rust extension
  (`26.70s` versus baseline `8.02s`), because cost moves into Rust
  path-build/metadata copy-boundary work.
- Keep Rust routing work narrow: potential-only/cache amortization first,
  path-build/metadata later only if their release-profile evidence improves.
- JAX remains a GPU tensor watchlist for dense flow/scoring only. The current
  row-local and fixed graph cost-to-go NN hypotheses are closed by PR49/PR51.
- PR47 confirms real RTX 3080 Ti acceleration for frozen-input 512-step dense
  flow chunks at 4,096 and 16,384 links after warmup. The 65,536-link case fails
  the fixed `1e-3` drift gate. Per-tick host synchronization and mutable runtime
  inputs remain unmeasured, so no JAX runtime flow backend is authorized.
- PR48 replaces identifier-only cost-to-go rows with a versioned NumPy feature
  contract and target-independent grouped split. The feature surface is
  row-local and experiment-only; it does not establish cross-city
  generalization or authorize an NN backend. Final gate: `522 passed`; all
  three review perspectives, Ruff, and diff checks are clean.
- PR49 audits 64,968 rows across nine planar generated maps and two dynamic
  states. Row retention, dynamic response, and deterministic seed holdout pass,
  but the fixed near-duplicate relation gate fails (`0.6907` conflict versus
  `0.25` maximum). A row-local MLP is not authorized. The result is accepted as
  diagnostic-only after three review perspectives; final gate: `547 passed`.
- PR50 implements a NumPy-only directed graph sample, memory-bounded padded
  batch, and explicit static-network holdout contract. It is accepted after
  spec/code/drift review with a `560 passed` final gate. It authorized only the
  now-completed PR51 experiment, not a runtime NN backend.
- PR51 runs the fixed JAX/Optax graph-aware versus row-local control on the RTX
  3080 Ti. Mean normalized-MAE ratio is `1.0581`, no model seed reaches the
  `0.90` gate, and repeat determinism fails. The formal result is inconclusive,
  but the independent accuracy miss stops graph-NN tuning and runtime promotion.
  All three review perspectives are closed; final gate: `570 passed`.
- The pulled runtime-closure proposal at `46f0fd7` is accepted only with the
  corrective commits `44d1145`, `505bb11`, `e30af45`, `368e719`, and
  `eb042bc`. The review artifact is
  `artifacts/runtime_spine_review/external-proposal-validation-20260712.md`.
- Static legal turn-pair lookup and same-tick reroute potential/selection reuse
  remove proven duplicate work. The seed-41 10k workload falls from 77.1 s to
  16.0 s with unchanged terminal counts. At 100k, cadence reroute remains a
  material parent-stage cost and the 240 s bounded run does not close.
- JAX dense-flow equations again match the NumPy/Rust point-queue contract.
  Steady 16,384-link GPU chunks are faster locally, but compile/copy-inclusive
  first execution remains slower than NumPy, so runtime promotion is not open.

## Open Risks

- **The audited runtime-closure blocker is closed only at a bounded internal
  level.** Finalized generated networks now expose exhaustive typed turn
  authority, active route tails produce turn/sink demand, and exact realized
  tokens update agents and queue mass together. In the seed-41 20-tick probe,
  all 15 routable trips complete, one no-route trip fails explicitly, and both
  active agents and queue mass end at zero with no invariant failure.
- Two independently initialized seed-41 20-tick runs also produce the same
  canonical final-state fingerprint. The digest covers full config, static
  routing authority, and replay-authoritative dynamic state including
  service/receiving/turn residuals, sink flow, demand lifecycle, and agent state;
  host timing diagnostics are excluded.
- Sink and internal-turn requests share a deficit scheduler rather than fixed
  internal-first priority. Runtime invariants independently recheck both source
  service and downstream receiving tokens, and final-link completion requires
  the link endpoint to equal the declared agent destination.
- Discrete token/residual metadata is required after the authority activates.
  Missing, non-finite, negative, non-integral, shape-inconsistent, or divergent
  link/node sink tokens fail closed rather than being overwritten next tick.
- That historical probe is not a 100k run or physical traffic validation. The
  default point queue still advances at most one route turn per tick. The new
  explicit NumPy `spatial_queue_v1` instead treats `progress_01` as link
  residency and enforces finite storage/source/downstream spillback, but it is
  not calibrated for real traffic, shockwaves, or lane-level behavior.
- The new exact per-turn agent contract remains Python-authoritative. Explicit
  unsupported Rust agent/flow paths fail closed; Rust parity and performance
  must be re-established on the new contract before promotion.
- Exhaustive turn compilation creates 51,886 rows for seed 41. A local
  developer measurement observed about 30% generation-time and 17–22 MB RSS
  overhead; this is diagnostic, not a controlled scale benchmark.
- Broader local evidence now covers ten seeds and a closed 10k run, but the
  100k seed-41 run reaches only tick 128 within the 240 s limit. At that point
  20,280 trips are complete, 163 are classified no-route, 10,626 remain active,
  and observed queue/agent mass is still exact. This is bounded progress, not a
  successful 100k validation.
- Runtime replay now binds ordered controls, the actual RNG key, and step count,
  and transition witnesses reconcile flow-input queue, realized flow, output
  queue, and sink completions. Replay result arrays are detached/read-only, but
  the stored fingerprint remains the final integrity authority for Python
  object snapshots.
- The realistic-city compiler remains explicit and deterministic, but PR62
  blocks default promotion: its six-style by five-seed audit passes `0/30` maps.
  Mean node degree and dead-end share fail on every map, seven maps exceed the
  800 m developed branch-free corridor gate, and the contact sheet confirms a
  repeated triangular local fabric with zero collector length share. Do not
  relax the pinned envelope or describe the generator as morphologically
  plausible until the street/block growth algorithm changes.
- PR63 also blocks default promotion. Its fresh-process 1k/10k/100k matrix
  finds 100k generation at `2.55-2.77x` legacy, underfilled citizen populations
  in both modes, and lower equal-budget realistic throughput on every seed.
  Generation RSS and fixed-step latency ratios pass, but no eligible generation
  stage clears the all-seed 30-percent Rust gate. Performance work cannot
  substitute for the PR62 morphology redesign.
- `SimulationState.simulation_step` does not run the legacy accessibility and
  land-use cadences. The new runtime and frozen `WorldState` orchestrator remain
  split authorities rather than one city-to-traffic-to-LUTI loop.
- Smoke eager workloads may overrepresent activation/allocation cost.
- Nested timing shares overlap and must not be summed as exclusive wall-clock
  partitions.
- Repeated instrumentation can become a local-minimum trap if it no longer
  changes the next implementation decision.
- Static hardware-fit labels are not performance evidence unless linked to
  runtime stage timings or copy-inclusive microbench results.

## City Map State

- Typed physical centerlines, road sections, node interfaces, width-aware SVG
  ribbons, and offline no-network OSM XML import are implemented.
- `sidecar_local_fabric_planar` is an explicit fail-closed review mode with
  endpoint, intersection, section, sampled-OD, and replay gates.
- `standard` remains the runtime default. A planar default trial raised the full
  suite from about 48 seconds to 281 seconds and broke a route-ID regression.
- The final planar seed-44 image is topologically legal but still visually
  dominated by sparse hub clusters and long direct corridors. Morphology realism
  remains open and is not solved by further renderer or planarization work.
- PR42 adds a three-seed physical-network quality envelope and a versioned,
  narrowly scoped structural gate. Staggered streets reduce excess four-way
  intersections without cutting network continuity, and river return streets
  reduce corridor dead ends. The new visual audit still shows isolated precinct
  patches separated by bare inter-district links, so citywide continuity and
  morphology-aware land use remain open.
- PR43 adds global local-street cell presence and local-junction proximity,
  rejects a presence-only Goodhart failure, and supplies style-specific
  continuous infill. All explicit styles pass gate v2 across the deterministic
  matrix; integrated river audit leaves barrier crossings to bridge links.
  The maps remain schematic and are not named-city realism evidence.
- PR44 keeps legacy zone/POI placement as the default and exact fallback. The
  explicit morphology mode recomputes gate v2 against actual geometry, verifies
  bounded district/subcenter anchor provenance, preserves aggregate land-use
  contracts, and fingerprints the effective placement in runtime replay.
  Final gate: `493 passed`; Ruff and diff checks clean.
- PR45 reuses a public directed-pair reachability analyzer and the existing
  typed map renderer to audit morphology land use. Across six styles and seeds
  17, 29, and 41, both legacy and morphology placement retain `1.0` POI access
  validity and directed representative-zone reachability. All aggregate
  contracts hold; zone centers all change and at least 99.7% of POI access
  nodes change. These are diagnostic results and do not authorize PR46. Final
  gate: `499 passed`; Ruff and diff checks clean.
- Canonical diagnostic bundle:
  `artifacts/city_continuous_fabric_20260711/` and
  `artifacts/city_continuous_fabric_quality_20260711/`.
- Land-use accessibility diagnostics:
  `artifacts/city_landuse_accessibility_20260711/` and
  `artifacts/city_landuse_accessibility_visual_20260711/`.

## Next Implementation Decision

Do not open another acceleration spec yet. Do not promote another runtime
backend either. Functional closure, broader generated/event conservation, and
replay-input/transition gates are green at small and 10k scale, while the 100k
bounded run remains incomplete. PR63 now additionally shows that the realistic
city path misses generation, realized-population, and equal-budget throughput
gates without identifying a single Rust-ready generation stage.
The explicit `spatial_queue_v1` physical traversal substrate is implemented,
but remains uncalibrated and cannot turn completed ticks into traffic-realism
evidence. Port the legacy medium/slow accessibility and land-use cadences into
`SimulationState` or explicitly retire that product claim.

The immediate product decision is PR64 fail-closed recording, followed by a new
generator specification that replaces the triangular local fabric and fixes
zone/home capacity so requested populations are realized. Only after PR62 and
PR63 are rerun should acceleration be reconsidered. Preserve four visible
lanes: Rust for branch-heavy graph/action planning, NumPy/SIMD for flow arrays,
JAX/GPU for amortized dense chunks/scoring, and NN only for simulator-labelled
surrogate experiments.
PR45 closes the current city-map lane without authorizing PR46. PR47 moves the
GPU dense-flow chunk to a bounded watchlist but does not authorize runtime
integration. PR49 rejects the row-local MLP path without threshold tuning;
PR50 freezes the graph tensor contract; PR51's fixed graph model also misses
its accuracy gate. Baseline Dijkstra remains authoritative. PR52's four-lane
owner step-back remains blocked until the post-closure replay/scale evidence is
refreshed on the functional workload.

External audit packet:
`docs/audit/metroflow_external_audit_20260711/README.md`.
