# Decision Log

## 2026-07-10: Acceleration Roadmap Closure Requires Fresh Evidence Before New Spec

Status: accepted

### Context

PR12 closed the spec-driven accelerated-runtime roadmap after PR08 through PR11.

### Compact CCoT

Question: What should happen after the roadmap closure?

Evidence: PR08 opened only an optional NN experiment harness; PR09 deferred
active-agent layout; PR10 and PR11 admitted zero-copy/Rayon and C++/CUDA only as
future evidence-gated work.

Inference: The next slice should not continue mechanically. It should begin
only after refreshed atlas or runtime benchmark evidence can change a
parent-stage decision.

Counterevidence checked: Several lanes remain plausible, but none is authorized
by roadmap closure alone.

Decision: Treat PR12 as a consolidation point. New implementation specs must
name the evidence they can falsify.

Falsifier: A new benchmark or atlas-linked decision card identifies a
parent-stage decision that changes under the existing guardrails.

Next action: Start the next spec from refreshed evidence, not from stale PR
momentum.

## 2026-07-10: C++/CUDA Requires One Narrow Evidence-Gated Kernel

Status: accepted

### Context

PR11 evaluated whether to add C++/libtorch/custom CUDA build surface for the
GPU/NN acceleration lane.

### Compact CCoT

Question: Should Metroflow add C++/CUDA/libtorch build surface now?

Evidence: Dense flow, route-score batch, and OD/policy batch are plausible GPU
targets, but current evidence does not identify one copy/compile-inclusive
kernel that clears the parent-stage gate.

Inference: The GPU lane should remain explicit and evidence-gated, with an
admission RFC before build complexity enters the project.

Counterevidence checked: RTX 3080 Ti 12GB and optional JAX/torch extras make GPU
experiments relevant, but hardware availability is not implementation
authorization.

Decision: PR11 is documentation-only. Future names `torch_cuda` and
`custom_cuda` remain documented but are not accepted runtime config values.

Falsifier: A dense flow, route-score batch, or OD/policy batch probe proves
copy/compile-inclusive parent-stage improvement across deterministic workloads.

Next action: Open PR12 to consolidate project state and handoff docs.

## 2026-07-10: Zero-Copy/Rayon Requires Copy-Boundary Evidence

Status: accepted

### Context

PR10 evaluated whether the current Rust CPU backend should move from Vec copy
boundaries to zero-copy NumPy FFI or Rayon parallelism.

### Compact CCoT

Question: Should Metroflow add zero-copy NumPy FFI or Rayon now?

Evidence: Current benchmark metadata records copy-boundary notes, but PR09
deferred active-agent layout and whole-runtime Rust routing remains blocked by
parent-stage path-build/metadata boundary costs.

Inference: The correct next step is an admission RFC, not new Rust dependencies
or parallel runtime behavior.

Counterevidence checked: Several Rust wrapper symbols are hardware-fit
candidates, but the atlas is diagnostic and cannot authorize implementation
without measured parent-stage evidence.

Decision: Keep PR10 RFC-only. Require copy-boundary timing to change a
parent-stage decision before opening zero-copy NumPy FFI or Rayon.

Falsifier: A deterministic benchmark proves that copy-boundary cost blocks a
review-ready parent stage after Rust compute itself is faster.

Next action: Open PR11 as the C++/CUDA Admission RFC.

## 2026-07-10: Active-Agent State Layout Recheck Deferred

Status: accepted

### Context

PR09 reopened the active-agent layout question only to check whether current
workload evidence authorizes another implementation slice.

### Compact CCoT

Question: Should PR09 implement active-agent state layout changes now?

Evidence: The deep runtime audit records `active_agent_pool_write`,
`active_agent_pool_array_write`, `active_agent_plugin_memory_write`, candidate
selection, and movement below the 0.30 review gate, while route candidate
refresh and dynamic-potential recompute remain review-ready.

Inference: Active-agent layout is still a watchlist item, not the next
implementation target.

Counterevidence checked: The hardware atlas still marks active-agent symbols as
possible CPU/Rust/NumPy fits, but atlas cards are diagnostic and require
runtime-stage or copy-inclusive evidence before implementation.

Decision: PR09 is docs-only: defer active-agent state layout implementation and
advance to PR10 Zero-Copy/Rayon RFC.

Falsifier: A broader deterministic workload or post-route-potential benchmark
makes typed-array pool replacement exceed the review gate across seeds.

Next action: Open PR10 as an RFC without adding zero-copy/Rayon build surface.

## 2026-07-10: Optional Route Surrogate Harness Is Experiment-Only

Status: accepted

### Context

PR07 added deterministic simulator labels for cost-to-go and route scoring. The
next PR may open the NN lane, but runtime route legality and fallback authority
must remain baseline/Rust.

### Compact CCoT

Question: How can the NN lane begin without changing simulator authority?

Evidence: PR07 labels provide schema-stable supervised targets. Guardrails allow
optional model experiments only with model/version/fallback metadata.

Inference: A small optional harness can summarize route-score labels and record
fallback metadata, while route legality remains unchanged.

Counterevidence checked: Adding runtime `torch_cuda`/NN backend config would
promote an experiment into authority before replay gates exist.

Decision: PR08 adds `torch` as an optional extra and a lazy experiment harness
only. Runtime backend registries stay unchanged.

Falsifier: If this PR imports torch at package import time or accepts runtime NN
backend values, revert.

Next action: Review, gate, and commit PR08 before considering active-agent state
layout recheck.

## 2026-07-10: Simulator Labels Before NN Surrogate Harness

Status: accepted

### Context

PR06 added route metadata/scoring batch probes but did not make JAX/NN route
authority. The guardrails require deterministic simulator labels before any NN
surrogate admission.

### Compact CCoT

Question: What should happen before an optional route/cost surrogate harness?

Evidence: Baseline dynamic potential and route candidate scoring already
produce deterministic cost-to-go and selected-route labels.

Inference: A schema-stable, simulator-only label dataset is the required next
substrate before any optional model work.

Counterevidence checked: Adding PyTorch/JAX training now would bypass label
provenance, fallback, and replay gates.

Decision: PR07 exports baseline-authoritative labels only. No runtime model
authority, external data, or new accelerator dependency is admitted.

Falsifier: If this PR reads external datasets or changes route legality/default
backend behavior, revert.

Next action: Add RED tests for label schema, determinism, JSONL stability, and
import boundaries.

## 2026-07-10: Route Scoring Probe Is Not Route Authority

Status: accepted

### Context

PR04 showed that broad whole-runtime Rust routing is premature because
path-build/metadata copy-boundary work can dominate. PR05 opened a dense-flow
probe without changing runtime backend values. The next watchlist lane is route
metadata/scoring shape evidence for NumPy/JAX/NN decisions.

### Compact CCoT

Question: How should K>1 route metadata, path-size scoring, and reroute scoring
be measured without changing route legality?

Evidence: Existing route candidate generation records candidate paths, path
costs, path-size factors, and selection metadata. Reroute scoring already has a
NumPy core and optional Rust explicit backend.

Inference: PR06 should add measured scoring batch probes, not a new routing
authority or runtime GPU backend.

Counterevidence checked: JAX/NN may fit dense score arrays, but cannot own graph
legality or state mutation without replay-safe labels and fallback.

Decision: Route scoring probes remain benchmark-only. Baseline/Rust authority
continues to own candidate legality and deterministic decisions.

Falsifier: If this PR adds runtime GPU/NN backend values or changes candidate
path legality, revert.

Next action: Add RED tests for K>1 metadata timing, path-size utility, reroute
batch shape, and optional JAX fallback metadata.

## 2026-07-10: Dense Flow Probe Is Benchmark-Only

Status: accepted

### Context

The workload matrix still marks dense flow/turn batches as requiring a
dedicated probe. The user wants GPU/NN lanes actively considered, but runtime
flow authority remains NumPy baseline with optional Rust CPU only.

### Compact CCoT

Question: How should dense flow compare NumPy, Rust, and JAX without changing
runtime backend policy?

Evidence: `FLOW_UPDATE_BACKENDS` is `("baseline", "rust_cpu", "auto")`, while
the hardware atlas lists dense flow as a NumPy/SIMD, Rust CPU, and optional
JAX/GPU candidate.

Inference: Dense flow needs a benchmark-only `probe_backend`, not a runtime
`flow_backend` expansion.

Counterevidence checked: Adding `flow_backend="jax"` would be premature because
JAX compile-vs-steady-state timing and copy behavior are not yet measured.

Decision: PR05 adds `jax_optional` only to the dense flow probe contract. Runtime
flow backend values remain unchanged.

Falsifier: If this PR changes runtime flow backend validation or adds CUDA/JAX
runtime dependency, revert.

Next action: Review, gate, and commit PR05 before opening route scoring probes.

## 2026-07-10: Rust Potential Bakeoff Must Stay Potential-Only

Status: accepted

### Context

Dynamic-potential recompute remains a review-ready route substage, while prior
whole-runtime Rust routing was slower because it included path-build and
metadata copy-boundary work. PR04 therefore needs a measured potential-only
contract before any routing-backend widening.

### Compact CCoT

Question: How should Rust potential be measured without re-authorizing
whole-runtime Rust routing?

Evidence: Existing route candidate benchmarks call full candidate generation,
which mixes potential recompute with greedy/ranked path building, route
metadata, selection, and fallback metadata.

Inference: A separate `measured_dynamic_potential` benchmark is needed to test
only the destination cost-to-go core and its Vec copy boundary.

Counterevidence checked: Whole-runtime Rust routing evidence remains negative
for the eager suite and must not be used as proof that the narrower potential
core is bad or good.

Decision: PR04 adds only the potential-only measured benchmark and parity
checks. Runtime routing defaults and route legality remain unchanged.

Falsifier: If the benchmark calls route-candidate generation, changes runtime
routing defaults, or treats smoke timing as validation, revert the PR.

Next action: Review, gate, and commit PR04 before opening dense-flow probes.

## 2026-07-10: Dynamic-Potential Cache Amortization Starts With Pruning

Status: accepted

### Context

PR02 linked workload matrix coverage to hardware-fit decision cards. The next
route-stage target is dynamic-potential recompute/cache behavior, but stale
route-potential reuse would be unsafe because link flow and event generations
affect travel costs.

### Compact CCoT

Question: What is the first safe dynamic-potential cache amortization step?

Evidence: Runtime route-potential keys already include network identity,
destination, max-hop/max-candidate policy, `runtime_flow_generation`, and
`runtime_incident_generation`. Existing route state can still retain older
cache entries after those signatures change.

Inference: Pruning stale entries and reporting cache size/prune counters bounds
runtime cache growth and makes invalidation auditable without changing route
legality.

Counterevidence checked: Removing flow generation from the key would improve
reuse, but it can reuse costs after queue/capacity changes and is therefore not
safe as a first slice.

Decision: PR03 will add Python-baseline pruning and observability only. It will
not widen dynamic-potential reuse across flow or incident generations.

Falsifier: If replay parity or candidate paths change for identical current
signatures, revert this slice before opening Rust/JAX/GPU route work.

Next action: Run targeted cache tests, runtime-spine tests, review loops, then
full gates before committing PR03.

## 2026-07-10: Spec-Driven Accelerated Runtime Roadmap

Status: accepted

### Context

The hardware-fit atlas links static code roles to runtime stage evidence and
shows that backend work must be selected by evidence, not repeated hot-path
inspection. The user requested a long-term PRD and PR list for
spec-driven/subagent-driven development.

### Compact CCoT

Question: How should Metroflow choose future Rust, NumPy/SIMD, GPU, and NN work
without drifting into repeated instrumentation?

Evidence: `artifacts/runtime_spine_review/hardware-fit-atlas.md` scanned 1105
symbols and linked 15 runtime stages. Guardrails require decision-changing
evidence before opening another backend slice.

Inference: Future acceleration work needs a roadmap with PR-level specs,
review-loop caps, and explicit anti-drift gates.

Counterevidence checked: The atlas is static planning evidence, not performance
proof. Runtime smoke artifacts remain diagnostic only.

Decision: Use `docs/PRD_ACCELERATED_RUNTIME.md` and
`docs/harness/ACCELERATION_PR_LIST.md` as the controlling roadmap for future
acceleration work. Future PRs must start with specs, run capped review loops,
and preserve baseline authority.

Falsifier: If a PR cannot identify an atlas decision card and falsifiable
measured probe, it must not implement backend logic.

Next action: Open PR01 Workload Matrix v1 before implementing another backend
slice.

## 2026-07-09: Runtime Acceleration Anti-Drift Guardrails

Status: accepted

### Context

Runtime benchmark instrumentation was refined through multiple slices. The deep
audit showed a stable conclusion across 1-step and 2-step eager suites:

- `active_agent_pool_write` is review-ready and dominates active-agent cost.
- `active_agent_candidate_selection` is not review-ready.
- `route_candidate_refresh` remains large, but its nested route potential/path
  build stages are both below the 0.30 review threshold.

### Metacognitive Self-Ask

Question: Are we repeatedly adding timing counters without changing the next
implementation action?

Evidence: The last two benchmark suites changed the explanation of
`active_agent_update`: first to allocation, then to pool write. That changed the
next action away from NN/JAX scoring and toward state-write/data-layout work.

Inference: One more split is justified only for `active_agent_pool_write`; more
route timing splits are not justified until pool-write is addressed or falsified.

Counterevidence checked: `active_agent_candidate_selection` remained near 3.5
percent in both 1-step and 2-step eager suites, so NN/JAX route-choice scoring is
not currently the hot-path fix.

Decision: Use `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md` as the
control document for future acceleration work and `/review`.

Falsifier: If a broader suite with longer horizon or larger K makes
candidate-selection or route metadata review-ready while pool-write falls below
threshold, reopen the NN/JAX path.

Next action: Split `active_agent_pool_write` into typed-array pool replacement
and plugin-memory dict update before implementing a backend optimization.

## 2026-07-09: GPU/NN Lane Kept As Watchlist, Not Runtime Default

Status: accepted

### Context

The user explicitly wants GPU+NN acceleration to remain an active project goal.
The benchmark evidence does not support making it the immediate hot-path fix.

### Decision

Keep JAX/GPU and NN surrogate lanes open as benchmark-gated watchlists:

- JAX/GPU: route scoring/metadata batches and dense flow update at larger scale.
- NN surrogate: dynamic-potential cost-to-go labels and route scoring labels.

Do not add PyTorch/libtorch/custom CUDA dependencies in the next slice.

### Review Note

Any `/review` that argues for GPU/NN must identify the exact scoring or dense
numeric stage it targets and show that it is not deterministic state mutation.

## 2026-07-09: Pool-Write Sub-Breakdown Redirects Next Slice

Status: accepted

### Context

`active_agent_pool_write` was split into:

- `active_agent_pool_array_write`
- `active_agent_plugin_memory_write`

The 1-step and 2-step eager suites both kept the parent `active_agent_pool_write`
above the 0.30 review gate. The plugin-memory substage was larger than the
typed-array substage but stayed below the 0.30 gate.

### Compact CCoT

Question: Should the next implementation be Rust pool-array write planning,
plugin-memory data-layout reduction, or NN/JAX scoring?

Evidence: In the regenerated eager suites, `active_agent_pool_write` stayed
review-ready, `active_agent_pool_array_write` stayed near 0.09 to 0.10 mean
share, `active_agent_plugin_memory_write` stayed near 0.26 to 0.28 mean share,
and `active_agent_candidate_selection` stayed near 0.03 to 0.04 mean share.

Inference: The parent pool-write stage remains the real active-agent issue, but
the first subproblem is Python plugin-memory mapping churn, not typed-array pool
replacement and not route-choice scoring.

Counterevidence checked: `active_agent_plugin_memory_write` does not clear the
0.30 review gate, so it is not a standalone accelerator target; it is a
data-layout cleanup target inside the review-ready parent stage.

Decision: Reduce dict-heavy selected-candidate metadata writes before opening a
Rust pool-array backend slice.

Falsifier: If metadata reduction does not lower parent pool-write cost, or if a
broader deterministic suite makes typed-array pool replacement the dominant
substage, reopen Rust pool-array planning.

Next action: Move hot selected-candidate diagnostics out of per-slot plugin
memory where possible, while preserving UI/replay-visible metadata behavior.

## 2026-07-09: Batched Plugin Memory Moves Next Slice To Route Path Build

Status: accepted

### Context

Allocation now accumulates plugin-memory updates during the trip allocation loop
and applies one immutable pool replacement afterward. This removes repeated
per-allocation plugin-memory pool reconstruction while preserving per-slot
metadata behavior.

### Compact CCoT

Question: Did the plugin-memory reduction lower the active-agent parent stage
enough to move to another bottleneck?

Evidence: In regenerated 1-step and 2-step eager suites,
`active_agent_pool_write` fell below the 0.30 review gate, while
`route_candidate_refresh` stayed review-ready and `route_candidate_path_build`
became review-ready in both suites.

Inference: Continuing active-agent pool-write work would now be local-minimum
behavior. The next review-ready CPU/control-flow target is route candidate
path-building.

Counterevidence checked: `active_agent_pool_array_write` remains visible, but it
does not clear the review gate. `active_agent_candidate_selection` also remains
small, so NN/JAX route-choice scoring is still not the immediate fix.

Decision: Move the next implementation slice to a narrow Rust CPU route
path-build contract, while keeping Python baseline route legality authoritative.

Falsifier: If path-build sub-analysis shows scoring or metadata dominates
instead of graph construction, stop before writing Rust graph code and update the
guardrails.

Next action: Inspect `routing.candidates` path-build internals and add RED
parity tests for the smallest Rust path-build boundary.

## 2026-07-09: Baseline Dijkstra Fix Redirects Route Acceleration To Potential

Status: accepted

### Context

The planned Rust path-build slice was step-backed after inspection showed Rust
greedy/ranked path-building already existed. Generated-OD micro analysis then
found a deeper issue: Python baseline dynamic-potential Dijkstra dropped valid
heap entries because heap costs were Python floats while authoritative
distances were stored as `float32`.

### Compact CCoT

Question: Should the next route slice still be Rust path-build?

Evidence: After fixing baseline Dijkstra `float32` heap-staleness, regenerated
1-step and 2-step eager suites show `route_candidate_potential` at `0.537567`
and `0.509388` mean share, while `route_candidate_path_build` falls to
`0.244385` and `0.231000`. Explicit Rust routing with a release extension
completed the 1-seed/1-step eager suite in `26.70s`, slower than the baseline
`8.02s`, with cost shifted into path-build and metadata copy-boundary work.

Inference: The previous path-build recommendation was a local-minimum artifact
of an incorrect baseline no-route behavior. The current review-ready route
substage is dynamic-potential recompute/cache behavior.

Counterevidence checked: Rust generated-OD micro routing matches the fixed
baseline path for OD node `422 -> 8`, and release Rust potential recompute is
fast. Whole-runtime Rust activation remains too slow because path-build and
metadata copy-boundary costs are not amortized.

Decision: Stop the whole-routing/path-build slice and move the next route work
to dynamic-potential recompute/cache amortization. Keep runtime-wide Rust
routing deferred.

Falsifier: If a narrow potential/cache slice fails to reduce route refresh, or
if a larger candidate-K workload makes path-build/scoring review-ready, reopen
path-build or NN/JAX scoring.

Next action: Add a generated-OD dynamic-potential benchmark/parity slice and
measure cache reuse by destination before opening another Rust route surface.

## 2026-07-10: City Map External-Source Boundary

Status: accepted

### Context

Static visual review showed that the current endpoint-line renderer and default
grid-derived topology cannot be repaired by importing a road-asset generator.
The reviewed CSUR repository supplies useful cross-section and segment-interface
concepts but is GPL-3.0 and delegates city-level placement and bending to the
game.

### Compact CCoT

Question: Should Metroflow directly absorb CSUR's road and city-map code?

Evidence: CSUR is a GPL-3.0 road-asset framework; Metroflow has no root license
decision, and its city-layout problem is upstream of road-section rendering.

Inference: Direct source absorption would add licensing and game-engine coupling
without solving centerline generation.

Counterevidence checked: CSUR's pure Python core is technically separable, but
technical separability does not remove provenance obligations or add city-scale
topology generation.

Decision: Keep a hard source boundary and implement Metroflow-owned geometry,
section, and node contracts from neutral behavioral specifications.

Falsifier: A separate explicit licensing decision authorizes GPL source reuse.

Next action: Implement PR34 typed road geometry contracts.

## 2026-07-10: Planar City Mode Remains Explicit

Status: accepted

### Compact CCoT

Question: Should the planar sidecar topology replace the runtime default?

Evidence: Explicit planar seed 44 reduces proper same-layer crossings from
2665 to zero and passes typed assignment, sampled-OD, and replay gates. A trial
default promotion increased the full suite from about 48 seconds to 281 seconds
and broke an existing route-ID regression. Visual review still shows sparse hub
clusters connected by long direct corridors.

Inference: Planarization closes a topology correctness gate but neither the
runtime budget nor morphology realism gate.

Counterevidence checked: The final reviewed suite passes after default rollback,
and the explicit mode remains available for visual and structural review.

Decision: Keep `standard` as default and admit
`sidecar_local_fabric_planar` only through explicit configuration.

Falsifier: A later generator/layout slice achieves realistic block morphology,
route-contract migration, and acceptable initialization cost across the required
seed matrix.

Next action: compare local-fabric morphology against offline OSM-derived
structural metrics before changing runtime defaults.

## 2026-07-10: Morphology Diversity Before Named-City Calibration

Status: accepted

### Compact CCoT

Question: Should generated-city realism continue by refining the radial layout
or by fitting one imported real city?

Evidence: The 100-city street-network literature reports a broad continuum of
orientation order, circuity, node degree, dead ends, and four-way intersections.
The PR41 comparison atlas confirms that one generator rule cannot represent this
range and that distinct grammar outputs can be measured without raw OSM runtime
dependencies.

Inference: The correct next substrate is a family of deterministic grammars plus
a common metric surface, not a universal radial model or a named-city clone.

Counterevidence checked: The six forms are visually distinct and pass planar
graph gates, but several remain sparse and their intersection mixes fall outside
the observed reference envelope. Metric separation alone is not realism.

Decision: Admit PR41 as diversity substrate. Keep empirical city values
reference-only, raw OSM offline, `auto` defaults unchanged, and all visual output
diagnostic-only.

Falsifier: If multi-seed PR42 tests show the styles collapse to the same block,
density, or intersection distributions, redesign the grammar boundary rather
than adding more preset names.

Next action: Implement block-continuity, street-density, connector-length, and
intersection-mix distribution gates before zone/POI morphology coupling.

## 2026-07-11: Citywide Coverage Before Land-Use Coupling

Status: accepted

### Compact CCoT

Question: Do the PR42 density and continuity gates justify morphology-aware
zone/POI placement next?

Evidence: Across seeds 17, 29, and 41, the targeted grammar changes improve
polycentric/mixed four-way shares and river dead-end/block-continuity metrics
without degrading the unaffected styles. The regenerated six-style contact
sheet still shows compact precinct islands connected by long bare links, while
district quadrant presence saturates at or near one.

Inference: PR42 validates local connectivity and intersection mix, but its
district-envelope metric is blind to inter-district gaps. Passing it is not
evidence of continuous citywide fabric.

Counterevidence checked: Convex-hull street density is nontrivial and sampled
OD/topology gates pass, but aggregate length and reachability do not establish
spatially distributed block fabric.

Decision: Scope the v1 gate explicitly to connectivity, density, and
intersection mix. Insert PR43 global spatial coverage and continuous corridor
fabric before PR44 morphology-gated zone/POI placement.

Falsifier: A deterministic global coverage probe shows the apparent gaps are a
renderer artifact rather than a centerline-distribution defect.

Next action: Add a probe that changes the infill decision, then implement
style-aware inter-district fabric only for failing styles.

## 2026-07-11: Reject Presence-Only Fabric Admission

Status: accepted

### Compact CCoT

Question: Is global local-street cell presence sufficient to admit continuous
fabric?

Evidence: The first infill draft raised presence above the proposed threshold,
but visual review showed wide X-shaped lines rather than coherent blocks. A
long-line synthetic cycle can also pass presence while having no local
degree-3 junctions.

Inference: Presence alone is vulnerable to Goodhart behavior and cannot own the
admission decision.

Counterevidence checked: The final style forms retain high presence, pass all
PR42 gates, and also distribute local junctions across a separate coarse raster.

Decision: Gate v2 requires both `0.40` local cell presence and `0.40` local
junction proximity with exact versioned raster parameters. Reject unknown
patterns and constrained corridors without valid barriers.

Falsifier: Morphology-aware land use exposes inaccessible or semantically
incoherent blocks despite both structural metrics passing.

Next action: Open PR44 with legacy-default placement, gate-based admission, and
replay/static-input fingerprint coverage.

## 2026-07-11: Admit Morphology Placement Behind Recomputed Evidence

Status: accepted after three review perspectives

### Compact CCoT

Question: Can accepted street morphology influence zone/POI placement without
weakening the NumPy baseline or deterministic replay authority?

Evidence: PR43 gate v2 passes the deterministic style matrix, but the first
PR44 review showed that trusting a stored `accepted` boolean and an arbitrary
64-character digest was forgeable. It also showed that district/subcenter
anchors were not bound to the gate and that equivalent immutable routing maps
could hash differently.

Inference: Morphology coupling is admissible only when current topology metrics
are recomputed, the complete gate matches, and the exact finite in-bounds anchor
payload is separately digested. Effective static placement must be hashed from
actual zones, POIs, and normalized routing maps rather than requested config.

Counterevidence checked: A stored gate can be stale or fabricated; a valid road
geometry fingerprint alone does not authenticate placement anchors; positional
dataclass fields and mapping representation can create compatibility or replay
drift. Regression tests now exercise each case and POI-only mutation.

Decision: Keep `legacy` as default and exact fallback. Admit explicit
`morphology_gated` only after current gate/anchor verification, preserve all
aggregate IDs/counts/capacities, and include placement plus gate provenance in
the replay boundary. No Rust, JAX, GPU, external-data, or demand authority is
added.

Falsifier: Multi-seed accessibility audit reveals inaccessible POI clusters,
unstable morphology separation, or demand distortion despite the structural
gate.

Next action: Open PR45 as a diagnostic zone/POI accessibility and visual-overlay
audit. Do not change demand sampling unless that audit changes the decision.

## 2026-07-11: Accessibility Audit Does Not Authorize Demand Expansion

Status: diagnostic accepted; PR46 not authorized

### Compact CCoT

Question: Does morphology-gated zone/POI placement introduce an access or
directed-reachability defect that requires downstream demand-policy work?

Evidence: Across six morphology styles and seeds 17, 29, and 41, legacy and
morphology placements each retain `1.0` POI access validity, `1.0` zone-node
coverage, and `1.0` directed representative-zone reachability. Aggregate IDs,
types, and capacities are preserved. Every zone center and at least 99.7% of
POI access nodes change. Static PNG review shows clearer district/subcenter
distribution but no zone polygons or parcel support.

Inference: PR44 placement is structurally distinct and no access blocker was
observed in this matrix. The audit is too weak to validate demand realism or to
justify a new demand-coupling policy.

Counterevidence checked: Weak connectivity alone was replaced by explicit
directed ordered-pair analysis; renderer zoning provenance is recomputed;
duplicate IDs and stale artifact directories fail closed. Full reachability is
still expected on these strongly connected generated networks.

Decision: Retain PR45 as diagnostic evidence only. Set `pr46_authorized=false`.
Do not continue with another renderer/reachability counter in the city lane.

Falsifier: A separate demand-defect or zone-spatial-support audit demonstrates
materially wrong trip distributions, inaccessible parcels, or unstable
placement behavior across workloads.

Next action: Step back to the Rust/control-flow, NumPy/SIMD, GPU tensor, and NN
surrogate lanes before opening the next implementation PR.

## 2026-07-11: Keep JAX Dense Flow At The Chunk Experiment Boundary

Status: diagnostic accepted; runtime backend not authorized

### Compact CCoT

Question: Does the dense-flow result justify adding a JAX runtime flow backend?

Evidence: On the RTX 3080 Ti, three-seed 512-step frozen-input device chunks at
4,096 and 16,384 links pass the predeclared warm first-call/copy, steady/copy,
and `1e-3` drift gates. The 65,536-link case reaches `0.0015769` maximum drift
and is rejected. Process/device warmup is about 873 ms and is reported
separately.

Inference: Persistent-device numeric chunks have a credible GPU acceleration
surface, but the measurement does not represent the current per-tick host
ownership and mutation boundary.

Counterevidence checked: The runtime applies event, route, active-agent, replay,
and immutable-state work around each flow update. Those synchronization and
checkpoint costs are unmeasured, and the largest measured shape fails the fixed
numeric gate.

Decision: Keep `runtime_flow_backend_authorized=false`. Preserve the lazy JAX
kernel as an experiment-only chunk probe, reject 65,536 links, and do not add
`jax` to the runtime flow backend contract.

Falsifier: An explicit checkpoint-cadence integration preserves replay and
state invariants while showing net parent-stage improvement across three seeds
without relaxing the numeric gate.

Next action: Switch lanes to PR48 and strengthen simulator-only cost-to-go
feature/label contracts before opening any NN training or runtime authority.

## 2026-07-11: Require A Leakage-Safe Feature Contract Before NN Fitting

Status: accepted after spec, code, and drift review

### Compact CCoT

Question: What substrate is required before a GPU cost-to-go surrogate result
can be interpreted?

Evidence: Existing PR27 rows expose node and destination identifiers, while the
authoritative target changes with geometry, directed topology, link travel
cost, effective capacity, and closures. Record fingerprints include labels and
cannot own split assignment.

Inference: Model inputs and split groups must be versioned and derived only
from input provenance before any fit/accuracy number is useful.

Counterevidence checked: A row-local feature vector does not encode full graph
adjacency and cannot establish cross-city generalization. Per-network
normalization is input-derived, not fitted from train/validation labels.

Decision: Add a NumPy-only 20-column feature contract, independent static and
dynamic fingerprints, raw distance diagnostics, and a target-independent
static-network/destination group split. Keep Dijkstra and route
legality authoritative.

Falsifier: Multi-city audit shows constant/degenerate features, destination
leakage, insufficient closure coverage, or a need for explicit adjacency and
edge tensors.

Next action: PR49 audits multi-city feature support. PR50 may fit a JAX model
only if PR49 authorizes the row-local contract; neither PR adds runtime
authority.

## 2026-07-11: Reject Row-Local Cost-To-Go MLP Before Training

Status: accepted

### Compact CCoT

Question: Does PR48's row-local feature contract contain enough target-related
information to justify a JAX MLP bakeoff?

Evidence: Nine planar generated maps, four destinations, and free-flow plus
stressed/closure states retain all 64,968 expected rows. Ninety percent of
features are nonconstant, 99.89% of matched rows change features and targets
together, and the seed-49 map holdout is feasible. However, 20.04% of rows enter
cross-map near-duplicate comparisons and 69.07% of covered rows conflict in
normalized target, exceeding the 25% maximum fixed in this PR before the
canonical run. This is not claimed as prior tracked preregistration.

Inference: The corpus and holdout are usable, but row-local inputs omit global
graph information needed to distinguish many authoritative costs.

Counterevidence checked: Closure-induced reachability loss was removed before
the canonical run; all rows remain. The conflict result is not caused by target
permutation or missing dynamic response. The fixed 25% threshold was not relaxed
after failure, but it has no earlier immutable preregistration record.

Decision: Do not open the row-local JAX MLP. Keep runtime NN authorization false
and replace PR50 with an adjacency/edge-state tensor contract. Move graph-aware
JAX fitting to conditional PR51.

Falsifier: A graph-tensor contract cannot preserve directed topology and dynamic
edge state in deterministic, memory-bounded batches without target leakage.

Next action: PR50 freezes directed graph tensors, padding/masks, fingerprints,
and map holdout inputs without fitting a model.

Review closure: `/review-spec`, `/review-code`, and `/review-drift` report no
remaining findings after three bounded fix loops. Final gate: `547 passed`, Ruff
clean, and `git diff --check` clean.

## 2026-07-11: Freeze Graph Tensors Before Graph-Aware Training

Status: accepted

### Compact CCoT

Question: What graph-aware substrate is justified after PR49 rejects row-local
target identifiability?

Evidence: Baseline targets depend on directed topology, link travel cost, and
blocked state. PR49 supplies a viable map holdout but no evidence that a graph
model will be accurate or fast.

Inference: Model selection must wait until graph arrays, masks, batching,
fingerprints, and split provenance are deterministic and independently
reviewable.

Counterevidence checked: Tensor construction is not a performance benchmark and
does not resolve PR49's relation conflict by itself.

Decision: Add immutable NumPy graph samples, byte-bounded prefix padding, and an
explicit static-network split. Keep baseline Dijkstra as label and route-
legality authority; add no JAX model or runtime backend.

Falsifier: Directed edges or baseline targets cannot be reconstructed exactly
under masks, or static networks leak between train and validation.

Next action: Specify PR51's bounded JAX graph-aware versus row-local control
bakeoff. Runtime integration remains forbidden.

Review closure: all three review perspectives report no remaining findings.
Final gate: `560 passed`, Ruff clean, and `git diff --check` clean. The generated
861-node/3,120-edge batch smoke remains diagnostic-only.

## 2026-07-11: Do Not Promote The Graph Cost-To-Go Surrogate

Status: accepted diagnostic; no runtime promotion

### Compact CCoT

Question: Does PR50 graph context add held-out-map signal beyond a
parameter-matched row-local control?

Evidence: The fixed JAX/Optax experiment uses 72 graphs, the exact PR49 map
holdout, three model seeds, 30 epochs, and 16 shared reverse-message steps. The
graph/control normalized-MAE ratios are `1.0305`, `1.1823`, and `0.9615`; mean
ratio is `1.0581`, with `0/3` reaching the fixed `0.90` seed gate. The seed-41
repeat differs by `0.16173` in normalized prediction and fails determinism.

Inference: The formal state is `inconclusive` because determinism fails, but
the accuracy gate fails independently. Fixing determinism cannot make the
current fixed model satisfy the parent decision gate.

Counterevidence checked: One seed and several organic slices improve, but gains
are not stable across seeds/styles. Graph steady inference is about `2.30-2.33 ms`
versus `0.11-0.12 ms` for the row-local control. No runtime or real-city claim is
measured.

Decision: Do not tune architecture, epochs, seeds, or thresholds. Keep baseline
Dijkstra authoritative and stop the graph-NN lane before runtime integration.

Falsifier: None within PR51; changing the model would be a new hypothesis and
requires an owner-authorized future spec after a whole-lane step-back.

Next action: PR52 is an owner decision across distinct Rust/control-flow,
NumPy/SIMD numeric, JAX dense-flow checkpoint-cadence, and one future narrow
custom-kernel lane.

Review closure: `/review-spec`, `/review-code`, and `/review-drift` report no
remaining findings after two bounded fix loops. Final gate: `570 passed`, Ruff
clean, and `git diff --check` clean.

## 2026-07-11: Block Acceleration Until The Runtime Self-Drives

Status: accepted audit finding

### Compact CCoT

Question: Is the current integrated runtime functionally complete enough to
select PR52's next acceleration lane?

Evidence: Generated topology contains no turn-movement authority;
`build_initial_simulation_state` initializes zero turn demand; the flow engine
preserves zero demand and emits zero outflow; active-agent movement consumes
outflow budgets. In a seed-41 eager three-tick probe, 15 agents remain active
and 15 vehicles remain queued while turn demand, outflow, and movement stay
zero. Accessibility and land-use cadences exist only in the legacy
`WorldState` orchestrator.

Inference: Parent-stage acceleration evidence is being collected around a
runtime that does not execute its central generated traffic loop. Optimizing a
nested route/flow/backend stage now would repeat the local-minimum failure at a
higher architectural level.

Counterevidence checked: Handcrafted runtime tests can move agents when turns
and demand are injected, and isolated flow/Rust/JAX fixtures are valid. They do
not prove generated-city demand assembly or the integrated LUTI loop.

Decision: Block PR52 and all runtime backend promotion. Make typed turn
movements, route-derived turn demand, generated multi-hop movement, vehicle
conservation, and full-state replay the next specification.

Falsifier: A deterministic generated-city test demonstrates nonzero legal turn
flow, multi-hop movement/completion, conserved mass, and replay equality across
the complete dynamic state.

Next action: implement runtime closure in the NumPy baseline, then refresh the
hardware-fit atlas on the closed workload before choosing Rust, NumPy/SIMD,
JAX/GPU, or custom-kernel work.

## 2026-07-12: Close The Historical Self-Drive Blocker, Keep Product Claims Closed

Status: accepted bounded remediation; broader validation pending

### Compact CCoT

Question: Does the Python/NumPy `SimulationState` runtime now turn generated
routes into authoritative vehicle movement without losing queue or lifecycle
mass?

Evidence: Finalized generated topology now compiles exhaustive deterministic
incoming-by-outgoing turn rows with explicit forbidden immediate returns.
Before flow, active route tails build exact turn and sink demand; after flow,
agents consume only their matching realized turn/sink tokens. Source service
and downstream receiving rates use deterministic integer tokens with fractional
carry. The seed-41 20-tick probe compiles 51,886 rows, completes all 15 routable
trips by tick 16, records one explicit no-route failure, and ends with zero
active agents and queue mass. Every tick passes invariants and exact per-link
agent/queue equality.

Two independently initialized seed-41 20-tick replays also produce the same
canonical final-state fingerprint and replay telemetry. The digest includes
full config, static routing authority, service/receiving/turn residuals, sink
flow, demand lifecycle, and active-agent state while excluding host timing.
Sink and internal movements share the same deficit scheduler; receiving-token
excess is independently checked and final-link completion verifies the declared
destination endpoint.
Missing or non-finite token/residual metadata and non-integral vehicle tokens
are rejected before the next flow solve can erase the corrupted authority.

Inference: The specific 2026-07-11 route-to-turn-demand blocker is closed in the
authoritative Python baseline for the bounded generated workload. The old
`--expect-stalled` result remains revision-specific negative evidence.

Counterevidence checked: One small deterministic scenario does not validate
100k scale, arbitrary incidents/merge patterns, physical travel time, finite
storage/spillback, Rust per-turn parity, or a unified LUTI loop. Exhaustive turn
compilation also has a measured local cost of roughly 30% generation time and
17–22 MB RSS on seed 41.

Decision: Mark functional closure `INTERNALLY VERIFIED`, not scientifically or
operationally validated. Keep Python/NumPy authoritative, fail closed on the
unsupported Rust per-turn agent/flow contract, and keep PR52 blocked until the
closed workload has broader replay/scale evidence and a refreshed hardware-fit
decision.

Falsifier: Any generated/event replay shows missing or duplicate turn authority,
agent/queue divergence, lifecycle loss, source or receiving-capacity excess, or
non-deterministic residual/sink state.

Next action: broaden conservation and exact replay coverage, define physical
traversal semantics, measure turn/runtime scale cost, and either integrate or
retire the legacy accessibility/land-use claim before accelerator promotion.
