# Feature Specification: Urban Morphology Diversity

Status: implementation

## Goal

Expand generated-city structure beyond the legacy hub-and-spoke form by making
the existing city style contract select materially different street-network
grammars. The result must remain deterministic, replay-safe, and compatible
with the explicit planar review mode.

## Scope

- Add a literature-backed, reference-only corpus of observed city network
  metrics.
- Measure generated physical networks using orientation entropy/order,
  circuity, median segment length, mean node degree, dead-end share, and
  four-way-intersection share.
- Implement distinct `grid_core`, `polycentric_tod`, `river_constrained`,
  `superblock_mixed`, and `organic` sidecar morphology grammars while retaining
  `auto` scenario resolution as the compatibility default.
- Propagate the selected style and measured signature into static/runtime
  metadata.
- Generate diagnostic comparison maps. These are not validation evidence.

## Non-goals

- Reproducing or naming a synthetic city as a real city.
- Downloading OSM data at runtime or committing ODbL raw extracts.
- Learning parameters from external data.
- Promoting planar sidecar mode to the runtime default.
- Lane-level microscopic simulation.

## Acceptance

- Fixed seed and style produce identical geometry fingerprints and metrics.
- Every supported style passes topology, weak-connectivity, geometry, section,
  node-interface, planar-intersection, and sampled-OD gates in explicit planar
  mode.
- Generated styles do not collapse to one identical morphometric signature.
- Core imports remain independent of JAX, torch, CUDA, and Rust.
