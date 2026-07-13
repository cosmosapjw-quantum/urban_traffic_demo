# Feature Specification: Continuous Realistic Local Fabric

Status: implementation

## Goal

Generate orientation-field local streets throughout developed buildable cells
and connect every local component to the accepted hierarchical skeleton.

## Requirements

- Select bounded coarse local nodes from development intensity and buildability.
- Connect orientation/perpendicular neighbors only across buildable cells.
- Connect every local component to a non-bridge skeleton point with an explicit
  collector street or an exact shared-coordinate attachment; never use
  connectivity repair.
- Measure developed-cell road access on the terrain raster and fail when the
  maximum exceeds `400m`.
- Preserve deterministic physical units, provenance, and fingerprints.

## Non-goals

- No planar node compilation, block faces, zoning, runtime mode, or renderer.
- No external data, empirical claim, Rust/GPU backend, or legacy fabric change.

## Acceptance

- All six styles have local and collector streets, deterministic fingerprints,
  and maximum developed access distance at most `400m`.
- Local and collector streets never occupy water cells.
- Existing skeleton and legacy city tests remain green.
