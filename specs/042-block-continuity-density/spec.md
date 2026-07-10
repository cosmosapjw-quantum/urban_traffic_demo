# Feature Specification: Block Continuity And Density Envelope

Status: complete

## Goal

Turn the morphology atlas from a single-seed visual comparison into a
deterministic structural quality gate. Measure whether each generated style
forms continuous, spatially distributed street fabric without fitting a named
city or promoting a diagnostic artifact to validation evidence.

## Scope

- Measure physical street length per convex-hull area, length-weighted block
  continuity, connector/local length ratio, degree-type mix, and district
  envelope quadrant presence.
- Preserve directed-link deduplication and explicit units.
- Summarize every style across at least three deterministic seeds.
- Use the measurements to reduce excess four-way intersections in
  polycentric/mixed fabric and excess dead ends in corridor-constrained fabric.
- Expose the quality metrics in generator and morphology-atlas metadata.

## Non-goals

- Matching a named city or deriving thresholds from external city data.
- Treating static maps or this diagnostic envelope as runtime validation.
- Changing zoning/POI semantics in this PR.
- Adding Rust, JAX, torch, CUDA, or runtime backend configuration.
- Curved-centerline circuity work; endpoint-generated centerlines remain
  straight in this slice.

## Acceptance

- Fixed topology produces deterministic physical-network quality metrics.
- A cycle has full block continuity while a tree has none.
- Physical road length and class mix are not doubled by directed links.
- Every morphology style passes the existing explicit planar city contract.
- Multi-seed reports preserve per-seed values and aggregate min/median/max.
- Core imports do not load accelerator modules.
