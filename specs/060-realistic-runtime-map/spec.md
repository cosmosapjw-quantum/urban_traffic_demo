# Feature Specification: Realistic Simulation Map Compiler

Status: complete

## Goal

Compile the complete terrain-to-land-use blueprint into existing topology,
CSR, zoning, replay, initialization, and static-review contracts behind an
explicit fail-closed mode.

## Requirements

- Add `realistic_synthetic_v1` and `block_based_v1` as a legal paired config;
  preserve existing defaults and reject cross-mode combinations.
- Add immutable `CityBlueprint`, `RealisticCityQualityResult`, and
  `GeneratedCityMap` records with composed fingerprints.
- Add `generate_city_map(config, scenario_id, seed)` as the authoritative entry.
- Compile geometry, sections, node interfaces, exhaustive turns, bridge groups,
  CSR, and legacy-compatible zoning without connectivity repair.
- Require one weak component, zero proper intersections, complete compiler
  coverage, representative zone reachability, and 512 sampled reachable ODs.
- Route realistic initialization through the generated map exactly once and
  preserve blueprint/land-use fingerprints in replay/static metadata.
- Render realistic block polygons and block POIs in the static map payload.

## Non-goals

- No physical link traversal, default promotion, empirical plausibility claim,
  legacy generator rewrite, Rust/GPU backend, or connectivity fallback.

## Acceptance

- Six styles by seeds 17, 29, 41, and 44 pass quality and deterministic source
  contracts.
- Runtime initialization, replay, CSR, zoning, and static artifact smoke tests
  pass for the explicit realistic mode.
- Legacy and sidecar fingerprints remain unchanged.
