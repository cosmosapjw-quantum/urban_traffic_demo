# Feature Specification: Morphology-Gated Zone And POI Coupling

Status: accepted (`493 passed`; Ruff and diff checks clean)

## Goal

Make synthetic land-use placement respond to accepted city morphology without
changing the default deterministic baseline. Explicit morphology-aware mode
uses only simulator-owned topology metadata and falls back exactly to legacy
placement when admission evidence is absent or rejected.

## Scope

- Add `CityGenerationConfig.zone_poi_coupling_mode` with `legacy` default and
  `morphology_gated` explicit mode.
- Admit the new mode only from an accepted `morphology_quality_v2` gate whose
  geometry fingerprint matches the topology.
- Choose zone centers from synthetic district/subcenter anchors, fill spatially,
  and assign the unchanged zone-type multiset by deterministic morphology role.
- Preserve zone counts, type counts, capacities, POI type mixes, and stable IDs.
- Cycle POI anchors by spatial order only in admitted morphology mode.
- Fingerprint the complete static zone/POI placement in runtime replay bounds.

## Non-goals

- External data, learned land use, named-city calibration, or runtime OSM.
- Changing population/trip policy, simulation stepping, topology generation,
  runtime defaults, or any Rust/JAX/GPU backend.
- Making land use authoritative over route legality.

## Acceptance

- Default and explicit legacy placement remain identical.
- Fixed admitted input is deterministic and differs structurally from legacy
  while preserving aggregate counts/capacities.
- Missing, rejected, stale-version, or geometry-mismatched gates resolve to
  legacy placement with an explicit fallback reason.
- Replay static-input fingerprints differ for different POI placements on the
  same road topology.
- Core imports remain independent of optional accelerators.

## Review Closure

- `/review-spec`: closed forgeable stored-gate and unbound-anchor findings by
  recomputing current metrics and binding finite in-bounds placement anchors.
- `/review-code`: preserved positional dataclass APIs and normalized immutable,
  string-keyed, and reordered replay mappings.
- `/review-drift`: retained legacy authority and deferred demand changes to a
  separate accessibility audit; no accelerator or external-data scope added.
