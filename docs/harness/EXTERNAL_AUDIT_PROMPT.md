# External Adversarial Audit Brief

Repository: `https://github.com/cosmosapjw-quantum/urban_traffic_demo`
Branch: `codex/runtime-closure-remediation` (head `99103f9`)

> **This brief describes the tree at `d4f47f3`.** Remediation has since
> landed on the same branch: the morphology instrument now takes an explicit
> `MeasurementSpec` checked against a pinned `osmnx==2.1.1`, and every arm was
> re-scored into `morphology-control-table-v2-20260807.*`. The verdicts are
> unchanged by that repair -- 392 of 945 metric values moved, no verdict did --
> so the claims below remain worth attacking, but check them against head
> rather than against the numbers quoted here.

Baseline for the diff under review: `57805d9`

You can read the repository directly. Everything below is a claim to be
attacked, not a briefing to be trusted. Where a number is quoted, reproduce it
before relying on it, and say so if it does not reproduce.

---

## 1. What this project is, and where it is stuck

Metroflow is a deterministic urban traffic simulator (Python 3.12 + NumPy
authoritative, optional Rust CPU kernels, optional JAX). Its stated
precondition — a stable, realistic road network — has failed twice. Two
generators exist and both fail the project's own morphology gate. A third
approach (`growth_fabric_v1`) was added in this diff, passes that gate, and is
deliberately **not** wired into any runtime mode.

Runtime default is still `CityGenerationConfig.topology_mode="standard"`.

## 2. The single most important thing to attack

The previous cycle's failure was not primarily an algorithm failure. It was
that **the measuring instrument was never validated**, and the specs prescribed
an algorithm family that could not satisfy the thresholds frozen before it was
chosen:

- `specs/053` froze acceptance thresholds before any algorithm existed.
- `specs/057` then mandated "connect orientation/perpendicular neighbors",
  i.e. it specified a lattice stencil.
- `specs/058` mandated "convert every physical polyline segment to paired
  directed links", i.e. it specified the destruction of curvature.
- All 12 review records and all 12 commits for specs 053-064 carry the same
  date, and the plausibility instrument was built last.

**This diff claims to have fixed the instrument. That claim is the primary
target of this audit.** If the instrument is still wrong, everything measured
with it — including the favourable result for the new generator — is void.

## 3. Claims to attack, each with where to look

### C1 — The morphology metric now matches its reference definition
`src/metroflow/city/morphology_metrics.py`

Claim: the pinned Boeing 2019 corpus reports OSMnx values measured *after*
`simplify_graph` contracts degree-2 nodes, while the code counted every compiled
node, so node spacing rather than morphology controlled `mean_node_degree` and
`dead_end_share`. An opt-in contraction was added.

Attack: Is the contraction actually equivalent to OSMnx `simplify_graph`? Check
the junction-free ring case, parallel edges, self-loops, and whether orientation
should be binned per sub-segment or per simplified edge (the code chose
sub-segment; argue whether that biases entropy). Does the default-off choice
mean the runtime and the gate now measure different things, and is that
defensible?

### C2 — Envelope repair only ever tightens
`src/metroflow/city/plausibility_audit.py`

Claim: `[0.8*min, 1.2*max]` produced bounds outside the attainable range
(`orientation_entropy` upper 4.2984 vs a theoretical max of log(36)=3.5835, so
it could never fail). Clamping to theoretical ranges can only tighten.

Attack: Verify the "only tightens" property holds for every metric, not just the
tested ones. `orientation_order` is still reported vacuous (99.8% coverage) and
`circuity`'s floor still sits on its theoretical minimum — so two of seven
metrics still cannot fail in one direction. Is a 7-metric gate with two inert
bounds fit to authorize anything? Propose the replacement.

### C3 — The OSM positive control validates the gate
`artifacts/osm_control/`, `src/metroflow/benchmarks/morphology_control_table.py`

Claim: five real extracts (Chicago, Barcelona, Seoul, Tokyo, Charlotte) land
inside the envelope on all seven metrics, so the envelope is falsifiable and is
not the reason synthetic maps fail.

Attack: Five extracts of 6-12 km² each is a small, hand-picked control set, and
two of seven fetched (`paris`, `prague`) do not import at all — selection
effects are plausible. Are the bounding boxes representative or cherry-picked to
dense cores? Would peripheral or low-density extracts fail? Does the drive-network
filter match Boeing's methodology closely enough for the comparison to hold?
**A positive control that passes 5/5 on the first attempt deserves suspicion.**

### C4 — The discarded path outscores the rewrite
`artifacts/runtime_spine_review/morphology-control-table-20260807.md`

Claim: `sidecar_local_fabric` — frozen as the "negative control" in
`docs/PRD_REALISTIC_SYNTHETIC_CITY.md` on the strength of a contact sheet, never
measured — passes all seven metrics on 15/30 maps, versus 0/30 for the
`realistic_synthetic_v1` rewrite and 0/10 for the runtime default.

Attack: reproduce it. Then note the countervailing evidence: rendering
`sidecar_local_fabric`
(`artifacts/external_audit_2_maps/sidecar_local_fabric--superblock_mixed--s17.svg`)
shows
something that passes all seven metrics and is plainly not a city. Does that
invalidate the metric set, the claim, or both? What does it say about promoting
`growth_fabric_v1` on the same seven numbers?

### C5 — Growth produces what stencils cannot
`src/metroflow/city/growth_fabric.py`, `tests/test_growth_fabric.py`

Claim: accretive growth with snapping yields T-junctions, dead ends and
curvature by construction; scores 30/30.

Attack hardest here:
- The bulk of the tuning was done by sweeping parameters against the gate. How
  much of 30/30 is genuine morphology and how much is fitting to seven numbers?
  Design a held-out test the generator was not tuned against.
- `spacing_scale=3.0` and the district profile constants are authored, not
  derived. Are they overfitted to seed 17 / `polycentric_tod`?
- Determinism is asserted only via a geometry fingerprint on two seeds.
- `compile_grown_network` detects junctions by rounding coordinates to a
  1 m quantum. Argue whether that is robust, and what happens at 250 km².

### C6 — Known unresolved defects (verify these are stated honestly)
- **Street-length density is ~2.5x too high.** Generated 31.8 km/km² against an
  OSM-measured 5.3-13.9. Intersection density and all seven metrics are inside
  their bands, which is itself suspicious — explain how both can be true.
- **Local-street duplication 0.227** (near-parallel, direction-aware). A
  `redundancy_constraint_enabled` flag reduces it but collapses connectivity;
  the trade-off surface is recorded in the strict xfail in
  `tests/test_growth_redundancy_and_bypass.py`. The diagnosed missing mechanism
  is Parish-Muller *extend-to-cross*. Confirm or refute that diagnosis.
- **RAMP and BRIDGE are never emitted** (0 km each). Water stops growth instead
  of being bridged, so `river_constrained` maps are severed by their river.
- **Class mix is off**: arterial ~10.9% against a 12-15% reference, collector
  ~19% against ~10%.
- **Scale is unvalidated at target**: 250 km² generates in ~12 s but has not
  been run through the simulation.

## 4. Context that constrains any recommendation

- `road_class` appears **0 times** in `routing/`, `flow/`, `traffic/`,
  `demand/`. Hierarchy reaches the simulation only via
  `free_flow_speed_mps`, `capacity_veh_per_tick`, `lanes`, `length_m`.
- Signals are inert (`flow/engine.py` increments a timer, no phase logic),
  spillback is off in the default `point_queue_v1`, turn priority is uniformly
  1.0, and **route choice is disabled** (`route_max_candidates=1`).
- Per-lane capacity ratio is 1.33 : 1.22 : 1.00 for expressway : arterial :
  local, against an HCM-implied ~3.7 : 1.5 : 1.
- Measured: 3.47% of network length carries 76.2% of shortest-path length.
- A prior audit concluded the Boeing envelope may be **anti-correlated** with
  traffic realism: satisfying it strips local connectivity and pushes yet more
  flow onto the few skeleton streets. Attack or confirm this.
- `generator_v2.py` is the dispatcher for all four topology modes, so it cannot
  simply be deleted. `sim/init.py` imports the concrete `GeneratorV2` class.
- Rust: 10 stateless kernels passing owned `Vec<T>` with a `.tolist()` boundary;
  whole-subsystem Rust routing measured **26.16 s vs 7.46 s baseline**. An
  earlier analysis found an *infinitely fast* Rust replacement of
  `compile_planar_city_blocks` would only reach 1.92x while two Python
  memoizations reach 2.05x — so a Rust port of generation geometry looks
  unjustified. Check that reasoning.
- Forbidden by `docs/harness/CLAIM_LEDGER.md`: external-data learning; NN/RL/LLM
  as route-legality or state-mutation authority; smoke/PNG artifacts presented
  as scientific validation; silent fallback for an explicitly selected backend.

## 5. What we want back

1. **Instrument verdict first.** Is the calibrated instrument trustworthy? If
   not, stop there and say what must change — no generator advice is meaningful
   until it is sound.
2. **A ranked list of defects**, each with file:line, a reproduction, and a
   falsifiable statement of what is wrong.
3. **Concrete fix guidance for the density/duplication problem specifically** —
   this is the live blocker. Is extend-to-cross the right mechanism? If so,
   specify termination rules, ordering against the existing passes, and how to
   avoid re-introducing the connectivity collapse. If not, say what is.
4. **An opinion on the acceptance criterion.** The seven Boeing metrics are
   demonstrably insufficient (C4). Propose what a traffic-simulation-first gate
   should measure, given section 4.
5. **A promotion recommendation** for `growth_fabric_v1`: promote, hold, or
   reject, with the conditions attached.

Please state explicitly where you could not reproduce a claim, and where you
believe we have fooled ourselves. Findings that only confirm what this brief
already says are of limited value; the useful output is what it gets wrong.

## 6. Reproduction

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q     # 811 passed, 1 xfailed at d4f47f3; ~1000 at head.
                                  # The 9 xfails record measured, reproducible
                                  # defects, each failing on its own assertion.

# Control table across every arm plus the OSM positive control
.venv/bin/python -m metroflow.benchmarks.morphology_control_table \
  --artifact-prefix /tmp/control-table \
  $(for f in artifacts/osm_control/*.osm; do printf -- "--osm-extract %s " "$f"; done)

# The frozen prior evidence this diff disputes
.venv/bin/python -m metroflow.benchmarks.realistic_city_audit \
  --artifact-prefix /tmp/pr62-plausibility
```

Key entry points: `metroflow.city.growth_fabric.grow_street_network`,
`metroflow.city.morphology_control_table.score_street_morphology`,
`metroflow.city.plausibility_audit.build_empirical_metric_envelopes`.
