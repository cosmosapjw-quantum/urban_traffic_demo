# Origin, Motivation, And Research Intuition

## 1. Original Product Question

Metroflow began from a deliberately broad question: can one build an
explainable synthetic city of roughly 100,000 residents where road topology,
daily travel, mesoscopic congestion, route choice, incidents, accessibility,
and slow land-use response coexist in one deterministic simulation?

The original PRD rejects three shortcuts:

- a visually plausible road picture with no executable topology;
- pure shortest-path routing with no overlapping-alternative correction or
  incident response;
- same-tick coupling that lets traffic instantly alter accessibility, land use,
  or policy and thereby destroys causal interpretation.

The intended model was multi-rate from the beginning. Traffic evolves on a
fast tick, routing/accessibility on a medium cadence, and land use on a slow,
lagged cadence. Persistent citizens and schedules were meant to make demand
traceable. Candidate path K, path-size correction, conditional rerouting, event
effects, cache invalidation, and deterministic replay were meant to make route
choice inspectable rather than opaque.

Primary internal sources are `docs/PRD.md`, `docs/RESEARCH_SYNTHESIS.md`,
`docs/TRAFFIC_DYNAMICS_DESIGN.md`, and the constitution introduced in commit
`6524500`.

## 2. Why JAX Was Chosen Initially

The project was started with GPU and neural-network experiments in mind. The
first imported dependency set required JAX/JAXLIB, and the desired numeric
surfaces were naturally tensor-shaped: link-state evolution, batched route
scores, policy blends, and possible learned cost-to-go approximations.

That intuition was directionally reasonable but architecturally premature.
The initial executable code was dominated by tuple/scalar state, Python control
flow, graph traversal, and placeholder orchestration. In other words, the
dependency anticipated a future dense numeric workload that the code had not
yet established. Later work corrected this by making Python 3.12 + NumPy the
authority, isolating JAX as an optional extra, and requiring compile-versus-
steady timing and baseline fallback for every GPU experiment.

The current hardware hypothesis is more precise:

- Rust CPU for branch-heavy graph search and deterministic action planning;
- NumPy/SIMD for medium-sized dense flow/cost arrays;
- JAX/GPU, future PyTorch, or a narrow CUDA kernel only for large batched dense
  work whose transfer and synchronization costs are measured;
- NN only as a supervised approximation of baseline labels, never as route
  legality or state-mutation authority.

## 3. S2 Before S1

The governing phrase “S2 before S1” means semantic contracts and replay-safe
state transitions precede added realism or speed. It led to explicit units,
fail-closed optional backends, immutable-replacement conventions, multirate
scheduling, and cache invalidation metadata. This was a useful defense against
accelerating an unstable contract.

The limitation is that contract accumulation sometimes substituted for product
closure. Many interfaces are now carefully fingerprinted, while the integrated
runtime still lacks the route-to-turn-demand transformation needed to make
vehicles move. S2-before-S1 is sound only when each semantic layer is also
exercised end to end.

## 4. Donor Absorption And Re-Architecture

In July 2026 a large donor implementation was absorbed into the root package.
Commit `f0faf03` added 109 files and about 25,410 lines. The donor supplied much
of the city, flow, routing, demand, UI, and runtime substrate. Subsequent work
removed root dependence on the external `metro/` folder and made NumPy arrays
the public state authority.

This was productive: it moved the repository from a narrow edge-tick skeleton
to a broad simulator substrate. It also created the project’s largest
architectural risk. The absorbed `SimulationState` runtime and the original
`WorldState` multirate orchestrator were preserved side by side, and their
responsibilities were never fully reconciled. The repository currently has
working pieces for both, but not one closed model.

The git record cannot establish the donor’s full ancestry or authorship before
the import. The first commit itself is named `import repaired bundle`; there is
no earlier repository history in the supplied refs. External reviewers must
therefore treat pre-import origin and redistribution authority as unresolved.

## 5. City-Generation Intuition

The first city generator favored a deterministic radial/hub backbone. Visual
audit exposed that legal connectivity did not imply credible urban form.
Planarization removed crossings but increased initialization cost and broke a
route-ID regression. Directly absorbing CSUR was rejected because CSUR is a
GPL-3.0 road-asset/cross-section framework, not a city-scale centerline
generator, and Metroflow has no root license decision.

The city lane then moved toward project-authored typed centerlines, section
catalogs, node compilation, offline OSM XML reference import, six morphology
grammars, structural quality gates, continuous infill, and morphology-gated
zone/POI placement. The result is more diverse and structurally measurable, but
still schematic. It is not evidence that any named city has been reproduced.

The empirical morphology values cited in
`docs/map/URBAN_MORPHOLOGY_DIVERSITY.md` are reference context. Raw OSM data is
not runtime input and is not committed. This maintains the ban on external-data
learning but also caps validation at synthetic comparison.

## 6. Research Philosophy That Emerged

The project’s most defensible research contribution is methodological rather
than scientific:

1. preserve a deterministic baseline;
2. label smoke artifacts as diagnostic;
3. predeclare a falsifier before opening an acceleration slice;
4. keep negative results instead of moving thresholds;
5. separate implementation, parity, performance, and scientific-validity
   claims;
6. step back after repeated nested timing work stops changing decisions.

This philosophy produced useful negative findings: whole-runtime Rust routing
was slower; planar default was too expensive; the row-local NN feature surface
was non-identifiable; the fixed graph model failed accuracy and determinism;
and large dense JAX flow crossed the numeric drift gate. Those failures are
part of the project’s evidence, not defects to erase from its history.

## 7. Current Restatement Of The Goal

The next defensible goal is narrower than the opening vision:

> Close and validate one deterministic `SimulationState` loop in which
> generated trips produce legal turn demand, link/node flow advances agents,
> medium/slow accessibility and land-use updates occur on documented cadences,
> and replay reproduces the complete trajectory. Only then optimize measured
> stages or make 100k-scale claims.

GPU and NN remain active research lanes, but they should be reopened against a
functionally closed workload rather than the current partially synthetic
benchmarks.
