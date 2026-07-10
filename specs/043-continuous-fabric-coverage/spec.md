# Feature Specification: Continuous Fabric Coverage

Status: complete

## Goal

Detect and reduce the precinct-island pattern visible after PR42. A generated
style must distribute physical street fabric across its occupied convex hull,
not merely accumulate enough road length inside isolated district envelopes.

## Scope

- Add `global_street_cell_presence_share`, measured on a deterministic 24 by
  24 convex-hull raster with explicit resolution metadata.
- Add a 12 by 12 local-junction proximity diagnostic after visual review showed
  that long lines can satisfy presence without forming distributed block mesh.
- Prove that the metric separates a continuous lattice from dense isolated
  precincts with comparable total physical road length.
- Measure all six styles across deterministic seeds before changing grammar.
- Add style-aware continuous fabric: an orthogonal global lattice, radial mesh,
  rotated coarse superblock grid, district-tree bands, and barrier-aware
  corridor bands.
- Version the structural gate only after a broad project-owned threshold is
  justified by synthetic fixtures and multi-seed behavior.

## Non-goals

- Named-city calibration, external-data learning, or runtime OSM access.
- Zone/POI morphology coupling; PR44 remains blocked on this work.
- Renderer-only changes, lane-level simulation, Rust/JAX/GPU work, or runtime
  default promotion.
- Claiming that raster presence alone establishes full urban realism.

## Acceptance

- The continuous-lattice fixture has materially higher global cell presence
  than a comparable-length precinct-island fixture.
- Fixed topology, resolution, style, and seed produce identical metrics and
  fingerprints.
- Any infill change improves the parent global metric across at least three
  seeds without failing the PR42 gate, planar intersections, or sampled OD.
- All six explicit planar styles pass the versioned gate across the required
  seed matrix.
- Visual output remains diagnostic and records residual limitations.

## Falsifier

If the probe does not separate the synthetic fixtures or does not rank the
visually sparse styles below continuous fabric, stop generator edits and revise
the metric rather than tuning roads to the screenshot.
