# Adversarial Technical Audit

## Overall Assessment

**Health score: 71/100 (research prototype; not release-ready).**

Scoring uses a 100-point base for each reviewed dimension, with deductions of
15 for critical, 5 for warning, and 1 for suggestion. PR quality is not scored
because this history has no merge/PR record. Composite weighting is architecture
40%, debt 33%, and tests 27%.

| Dimension | Score | Main reason |
|---|---:|---|
| Architecture | 60 | one critical and five warning findings |
| Technical debt | 70 | generator monolith, duplicated surfaces, provenance debt |
| Test quality | 88 | broad suite, but no CI/Python lock/coverage and hardware skips |
| Composite | 71 | `0.40*60 + 0.33*70 + 0.27*88`, rounded |

This score is a triage aid, not a scientific metric.

## Findings

### Critical A1 - Generated-City Traffic Loop Is Not Closed

**Symptom:** Generated multi-link trips activate and enter source queues but do
not move. The generator emits no turn movements, initialization creates zero
turn demand, zero-turn flow returns zero outflow, and agent movement requires an
outflow budget.

**Source:** `city/generator_v2.py`, `sim/init.py`, `flow/engine.py`, and
`sim/routing_runtime.py`. Existing movement tests use handcrafted turns and
demand instead of a generated-city fixture.

**Consequence:** The new runtime spine cannot satisfy the core simulator claim.
Routing, agent allocation, replay, and acceleration metrics can all execute
around a traffic state that never propagates vehicles.

**Remedy:** Establish a typed `TurnMovement` authority in the compiled network,
derive deterministic per-turn demand from active route tails before flow, and
add a generated multi-hop test that proves movement, completion, and link-level
mass conservation. This blocks backend promotion.

### Critical D1 - City Generator Is A Tactical Monolith

**Symptom:** `city/generator_v2.py` is 5,654 lines and
`_build_preview_topology` spans approximately lines 462-4,799. Morphology fixes,
local infill, connectors, and acceptance logic accumulate in one control flow.

**Source:** Repeated feature slices added style-specific repairs without first
extracting a stable phase model. `district_mesh.py` adds many small bias helpers
that encode local patches rather than one explicit morphology grammar.

**Consequence:** Interaction effects are difficult to review, tests encourage
gate-specific tuning, and a morphology change can alter topology, IDs, runtime,
and visuals at once. Git records one contributor; operational bus factor was
not independently measured.

**Remedy:** Freeze current outputs, split generation into pure phase records
(`field`, `backbone`, `district fabric`, `repair`, `planarize`, `compile`,
`validate`), and make phase artifacts replayable. Do not add a seventh style
before extraction.

### Warning A2 - State Authority And Immutability Are Split

**Symptom:** Frozen tuple `WorldState` coexists with mutable, mostly `Any`-typed
`SimulationState` refs. Arrays and metadata dictionaries are writable and can
be aliased through internal constructors.

**Source:** `core/state.py`, `sim/state.py`, `flow/state.py`, and mutable dynamic
reference dictionaries.

**Consequence:** Cache fingerprints and replay integrity depend on convention,
not enforcement. Two runtime authorities also make feature ownership unclear.

**Remedy:** Select `SimulationState` as the only future runtime authority, use
typed frozen reference records, make authority arrays read-only at boundaries,
and retire `WorldState` only after its multirate semantics are ported and parity
tests pass.

### Warning A3 - Layer Direction Is Disordered

**Symptom:** Conceptual cycles exist across `city`/`map`, `city`/`sim`,
`demand`/`sim`, `routing`/`sim`, `routing`/`learning`, and `sim`/`ui`.
`sim.step` and `sim.init` directly import UI snapshots/buffers.

**Source:** Broad convenience imports and runtime-owned reporting hooks conflict
with `docs/ARCHITECTURE_OVERVIEW.md` layering.

**Consequence:** Core simulation cannot be reused headlessly without UI
knowledge, changes have high fanout, and circular local imports obscure true
ownership.

**Remedy:** Define ports for snapshot emission and label/scoring inputs. Move
composition to an application layer; keep core runtime independent of `ui`,
`benchmarks`, and experiment modules.

### Warning A4 - Routing Has Hidden Modeling And Correctness Limits

**Symptom:** Node potentials do not include incoming-link turn state; ranked-K
enumeration has a silent expansion ceiling; cadence reroutes are evaluated with
`incident_active=True`; and flow-state generation invalidates potentials very
aggressively.

**Source:** `routing/dynamic_potential.py`, `routing/candidates.py`, and
`sim/routing_runtime.py`.

**Consequence:** Turn penalties/restrictions can be approximated inconsistently,
candidate sets may truncate without a reviewer-visible reason, cadence behavior
can look like incident behavior, and cache amortization may be defeated.

**Remedy:** Make expansion truncation explicit in result metadata, distinguish
cadence and incident causes, document node-versus-edge-state legality, and add
targeted regression tests before further routing acceleration.

### Warning A5 - Demand, Learning, And LUTI Are Mostly Schematic

**Symptom:** `learning_enabled` mainly changes initial eager trip generation;
allocation hardcodes behavior profile 0; adaptive telemetry is constant; no
long-run trip generation or land-use update occurs in `simulation_step`.

**Source:** `sim/step.py`, `sim/routing_runtime.py`, and the split legacy
orchestrator.

**Consequence:** Names such as learning, accessibility, and land-use can imply a
coupled adaptive model that the current authoritative runtime does not execute.

**Remedy:** Downclaim current behavior, port one medium/slow cadence at a time,
and require a trajectory-level test showing the intended lag. Do not add an NN
policy until the deterministic loop is closed.

### Warning A6 - Replay And Invariants Are Incomplete

**Symptom:** Runtime invariants reconcile trip lifecycle counts but not complete
link-level vehicle mass. Replay has no single canonical digest covering all
dynamic state. Metric fields are manually repeated through step, summaries,
benchmarks, and UI.

**Source:** `sim/invariants.py`, `sim/replay.py`, summary/benchmark/UI adapters.

**Consequence:** A replay can match exposed counters while an un-fingerprinted
array drifts. Adding telemetry requires multiple synchronized edits.

**Remedy:** Add a canonical dynamic-state digest and conservation equation,
then generate reporting schemas from one typed metric record.

### Warning D2 - Accelerator Boundaries Duplicate Logic And Copy Data

**Symptom:** Python converts NumPy arrays to lists; PyO3 accepts owned vectors;
Rust reimplements multiple algorithms. The whole-routing Rust bakeoff is slower
than baseline despite a faster inner potential stage.

**Source:** `backends/rust_cpu.py` and `crates/metroflow-rust`.

**Consequence:** Parity burden grows with each semantic change, copy costs are
easy to undercount, and optimization may target code that is not on the closed
runtime path.

**Remedy:** Freeze Rust scope until functional closure. Reopen zero-copy/Rayon
only with copy-inclusive parent-stage evidence and one shared fixture contract.

### Warning D3 - Documentation And Claim State Drift

**Symptom:** At source baseline `96e54ca`, the README still called the project a
starter skeleton; the city PR list labeled completed PR44 as proposed; one
acceleration commit reference was mistyped; PR47-PR50 were absent from the
validation ledger; and there was no central claim ledger. This audit commit
corrects those current documents while preserving the historical finding.

**Source:** Many hand-maintained roadmap, state, validation, and artifact files.

**Consequence:** An external reviewer cannot tell current authority from stale
planning text without reconstructing git history.

**Remedy:** Make `PROJECT_STATE`, `CLAIM_LEDGER`, and `VALIDATION_LEDGER` the
only status authorities; generate cross-links and test known commit references.
This audit corrects the known PR-list errors but cannot reconstruct missing
independent attestations.

### Warning D4 - Reproducibility And Redistribution Are Incomplete

**Symptom:** No root license, CI workflow, Python/complete environment lock,
donor ancestry, or independent artifact attestation is present. Rust does have
a tracked `Cargo.lock`. Several experiment manifests omit
the generating commit, exact command, checksums, raw predictions, or weights.

**Source:** repository root, `pyproject.toml`, artifact manifests, and the first
`import repaired bundle` commit.

**Consequence:** A third party cannot safely redistribute the package or prove
that every canonical artifact came from the referenced source/environment.

**Remedy:** Resolve ownership and choose a root license before distribution;
pin environments; add CI; and make future canonical experiment bundles include
commit, command, environment, raw sufficient statistics, and checksums.

### Warning T1 - Tests Are Broad But Environment-Conditional

**Symptom:** The suite has 56 Python test files and 508 test functions, but no CI
matrix or Python/complete environment lock. GPU and extension tests can skip. Artifact snapshots can
become fixtures for their own report code.

**Source:** `tests/`, `pyproject.toml`, and absent `.github/workflows`.

**Consequence:** A green local suite does not prove base-only, Rust, and GPU
lanes on fresh machines.

**Remedy:** Add base-only and Rust CI jobs first; publish skip counts; isolate
artifact renderer tests from independent numerical recomputation.

### Warning T2 - Product-Critical Generated Movement Is Not Tested

**Symptom:** Movement tests inject handcrafted turns/demand and therefore bypass
the generated-city turn gap.

**Source:** `tests/test_runtime_spine.py` fixtures.

**Consequence:** Hundreds of passing tests coexist with a stalled integrated
simulation.

**Remedy:** Add one generated-network, generated-trip, multi-hop trajectory test
before increasing coverage elsewhere.

### Suggestions

- Add coverage and pytest marker configuration so hardware/slow/diagnostic
  categories are visible.
- Add property/fuzz tests for Rust index/length validation and Python/Rust
  conservation parity.

## Positive Findings

- Baseline fallback and explicit backend failure semantics are consistently
  tested.
- Replay fingerprints cover more configuration and cache metadata than most
  prototypes at this maturity.
- Negative experiment results are retained and thresholds were generally not
  relaxed after failure.
- Static visual audit caught both disconnected topology and a morphology gate
  that could be gamed.
- The hardware-fit atlas and anti-drift rules explicitly separate static
  classification from performance authorization.

## Release And Research Gates

| Gate | Current state |
|---|---|
| Generated trips move and complete | **blocked** |
| Link-level mass conservation | **not demonstrated** |
| One authoritative multirate runtime | **not implemented** |
| Deterministic local replay | internally verified, incomplete digest |
| Base/Rust parity | internally verified for isolated kernels |
| GPU runtime backend | not authorized |
| NN route surrogate | rejected for tested hypotheses |
| 100k integrated scale | not demonstrated |
| Real-city morphology/traffic validation | not performed |
| External redistribution | blocked by license/provenance |

## Recommended Priority

1. Introduce turn-movement authority and close generated traffic movement.
2. Add complete mass/replay invariants and a generated multi-hop acceptance
   test.
3. Port multirate demand/accessibility/land-use into `SimulationState` and
   deprecate the legacy spine.
4. Decompose the city generator into phase artifacts.
5. Only then refresh hardware-fit measurements and choose a Rust/NumPy/GPU
   optimization lane.
