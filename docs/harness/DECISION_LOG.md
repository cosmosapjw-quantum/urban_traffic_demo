# Decision Log

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
