# PRD - Realistic Synthetic City

Status: active contract
Last updated: 2026-07-13

## Product Goal

Metroflow must generate a deterministic, morphologically plausible functional
2D city whose roads, blocks, land use, points of interest, and terrain
constraints compile into the existing traffic runtime. The target is a
synthetic city family, not a named-city replica.

The Python 3.12 and NumPy path remains authoritative. Static images are product
review surfaces only. Real-city aggregates may define broad comparison
envelopes, but they are not training inputs and cannot authorize empirical
traffic, demand, route-choice, or land-use claims.

## Current Negative Control

The accepted `sidecar_local_fabric_planar` path supplies typed centerlines,
sections, node interfaces, planar topology, six morphology styles, deterministic
zone/POI placement, sampled OD reachability, and replay fingerprints. The
canonical 2026-07-11 contact sheet still shows schematic precinct clusters,
long exposed connectors, highly regular local motifs, and no block or terrain
authority. It is the frozen negative control for this roadmap.

The current `standard` path remains the runtime default. A previous planar
default trial materially increased the full-suite runtime and broke a route-ID
regression. No realistic-mode work may silently change this default.

## Runtime Contract

- `CityGenerationConfig.topology_mode="realistic_synthetic_v1"` explicitly
  requests the new path. Failure is fail-closed; no legacy fallback is allowed.
- `generate_city_map(config, scenario_id, seed)` returns an immutable
  `GeneratedCityMap` containing its blueprint, compiled topology, zoning, and
  quality result.
- `GeneratedCityMap.topology` compiles to the existing `PreviewCityTopology`
  and `RoadNetworkCSR` contracts consumed by routing, flow, replay, and UI.
- `GeneratorV2.generate_preview_topology()` remains a compatibility facade.
- `zone_poi_coupling_mode="block_based_v1"` is legal only with the realistic
  topology mode. Existing legacy and morphology-gated results remain stable.
- A versioned blueprint fingerprint binds seed, style, extent, terrain, urban
  form, physical roads, blocks, land use, and POIs.

## Fixed Generation Stages

The new path uses a fixed typed pipeline rather than a generic plugin system:

1. bounded NumPy terrain and development fields;
2. deterministic centers, gateways, and morphology orientation fields;
3. terrain-aware hierarchical street skeleton;
4. continuous local fabric inside developable regions;
5. planar compilation and bounded-face block extraction;
6. block-based land use, capacity, and POI allocation;
7. road geometry, sections, node interfaces, turns, and CSR compilation;
8. fail-closed quality and simulation-input validation.

New behavior must not be appended to the monolithic legacy builder in
`generator_v2.py`. Compatibility wrappers may remain there while the new
pipeline lives behind typed stage boundaries.

## Frozen Acceptance Thresholds

These thresholds may be changed only by a new spec with contradictory evidence;
implementation PRs PR54-PR64 must not tune them to make a seed pass.

| Gate | Requirement |
|---|---|
| weak components | exactly `1` |
| connectivity repair links | exactly `0` in realistic mode |
| same-layer proper intersections | exactly `0` |
| geometry, section, node-interface, turn coverage | `100%` |
| representative and 512 sampled directed OD reachability | `100%` |
| maximum developable-cell road access distance | `400 m` |
| maximum branch-free developed corridor | `800 m` |
| physical segment median | `40-180 m` |
| physical segments shorter than `10 m` | at most `2%` |
| bounded-block median area | `3,000-30,000 m2` |
| bounded-block p95 area | at most `120,000 m2` |
| developed block road frontage | `100%` |

For pinned empirical street-network metrics, the comparison envelope is
computed mechanically as `[0.8 * reference_min, 1.2 * reference_max]`, clamped
to `[0, 1]` for shares and with circuity bounded below by `1`. The envelope is
diagnostic plausibility evidence, not named-city calibration.

## Promotion Gate

The new mode remains explicit until all correctness, replay, visual-product,
and scale gates pass. Relative to the frozen legacy workload, 100k generation
must be at most `2x` wall time and `1.5x` peak RSS; the 20-tick parent runtime
stage must be at most `1.25x`; and a bounded 100k run must not advance fewer
ticks in the same wall-time budget.

Promotion does not authorize empirical traffic realism. Physical link
traversal, finite storage, and spillback require their own explicit runtime
contract before tick completion can be interpreted as physical travel.

## Claim Boundary

Allowed after the corresponding gates pass:

- deterministic realistic-mode substrate;
- structurally plausible synthetic street and block distributions;
- simulation-compatible topology and static land-use input.

Still forbidden without independent evidence:

- replication of a named city;
- empirically validated traffic, demand, route choice, or LUTI behavior;
- external-data learning or runtime OSM fetching;
- PNG/HTML smoke artifacts presented as validation;
- CSUR or other donor-source compatibility claims;
- lane-level microscopic or full public-transit assignment claims.

## Review Contract

Every PR requires `/review-spec`, `/review-code`, and `/review-drift`, with at
most three finding/fix loops. A PR with unresolved findings is marked blocked
and is not committed. Renderer-only work and connectivity-repair masking are
not admissible. After two consecutive PRs in one detail lane, review must step
back across terrain/growth, topology, land use/demand, and simulation physics.
