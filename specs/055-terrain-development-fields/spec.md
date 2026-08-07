# Feature Specification: Terrain And Development Fields

Status: implementation

## Goal

Add bounded, immutable NumPy terrain and urban-form fields that can drive the
realistic generator without changing any accepted topology mode.

## Requirements

- Terrain extents and cell sizes use meters and raster dimensions never exceed
  `256x256`.
- Elevation, slope, water, buildability, development intensity, and orientation
  fields are finite, contiguous, exact dtype, and read-only.
- Six registered morphology styles produce deterministic centers and
  orientation fields from project-owned profiles.
- Water cells are never buildable or developed.
- Fingerprints bind schema, extent, seed, style, centers, and full arrays.
- Core imports remain independent of optional accelerators.

## Non-goals

- No roads, blocks, zones, runtime topology mode, external data, or calibration.
- No GPU/Rust backend or generic field plugin system.

## Acceptance

- Fixed seed/style fields and fingerprints repeat exactly.
- Seed and terrain-relevant style changes alter fingerprints.
- Invalid extents and grid bounds fail closed.
- Existing city behavior and full test suite remain unchanged.
