# City Map Source Provenance

Status: active source boundary
Last updated: 2026-07-10

Machine-readable policy: `docs/map/city_map_source_policy.json`

## Decision

Metroflow does not vendor, import, or copy source from the GPL-3.0
`citiesskylines-csur/CSUR` repository. The repository is used only as a
reviewed reference for neutral road-design concepts. Metroflow's
implementation must be authored from its own contracts and tests.

This boundary is mandatory while the Metroflow repository has no explicit
GPL-compatible distribution decision. It is an engineering provenance gate,
not legal advice.

Reference snapshot reviewed during planning:

- repository: `https://github.com/citiesskylines-csur/CSUR`
- commit: `a47270e0a20ff5bda23db3d7db34a993b36c9a69`
- upstream license: GPL-3.0

## Permitted Neutral Concepts

- A road cross-section is composed from typed units with explicit widths.
- A segment has independently described start and end cross-sections.
- Segment interfaces may be classified as base, lateral shift, lane
  transition, or ramp.
- Interface construction validates lane-count deltas, lateral alignment, and
  median or separator continuity.
- Equivalent profiles receive a deterministic canonical identifier.

These concepts must be restated in Metroflow terminology, with Metroflow
units, invariants, and test cases. Upstream code fragments, class layouts,
name encodings, and magic constants are not permitted inputs to implementation
tasks.

## Excluded Source Surfaces

- `modeling/` Blender mesh generation
- `graphics/` Cairo sprite generation and bundled binaries
- `prefab/` Unity XML and asset packaging
- `bin/` game runtime binaries
- exhaustive asset-release enumeration from `builder/`
- Cities: Skylines segment-length, prefab, or game-engine assumptions

CSUR is not a city-scale centerline or topology generator. It generates road
asset configurations and delegates network placement and bending to the game.
Metroflow therefore keeps centerline generation, topology compilation, road
section compilation, and node-interface compilation as separate authorities.

## Independent Implementation Rule

1. A Metroflow spec records required behavior without upstream code excerpts.
2. Tests are written from that spec and project invariants.
3. An implementer receives the Metroflow spec, not the upstream repository.
4. Review checks imports, dependency metadata, copied identifiers, and
   unexplained constants.
5. Any proposal to vendor or adapt upstream source stops pending an explicit
   repository licensing decision.

## Claim Boundary

- **VALIDATED:** the reviewed CSUR snapshot is GPL-3.0 and describes itself as
  a road-asset generation framework.
- **SPECIFIED:** Metroflow will implement its own typed road-section grammar.
- **IMPLEMENTED:** caller-supplied offline OSM XML can feed the same typed
  centerline/section compiler through a standard-library, no-network adapter.
- **PROPOSED:** tensor-field centerlines may feed the same compiler.
- **FORBIDDEN:** claiming that CSUR provides a complete city-map generator or
  that Metroflow already implements CSUR-compatible assets.

The OSM adapter records the exact input SHA-256 and declared XML version. It is
reference/development tooling only; it is not imported into default city init,
does not fetch data, and does not validate the synthetic generator by itself.

Historical `csur_module_*` metadata keys were deprecated, non-evidentiary
diagnostic labels, not compatibility claims. PR35 removed them from runtime
sources in favor of project-owned `road_hierarchy_module_*` names. Historical
artifacts are not rewritten.
