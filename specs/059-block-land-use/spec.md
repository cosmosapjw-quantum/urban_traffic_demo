# Feature Specification: Block Land Use And POIs

Status: complete

## Goal

Assign deterministic functional land use, capacities, access nodes, and POIs
to accepted planar blocks without external data or legacy centroid zoning.

## Requirements

- Classify every block as residential, commercial, mixed use, industrial, or
  open space from development intensity, center proximity, slope, and arterial
  exposure.
- Keep water, non-buildable, and negligible-development blocks open space.
- Give every developed block an access node on its road frontage.
- Prevent industrial and residential blocks from sharing a boundary; mixed or
  commercial blocks may act as buffers.
- Give every residential block deterministic home and leisure POIs and retain
  at least one home, workplace, and leisure POI citywide.
- Derive population, job, and leisure capacities from explicit block area and
  per-hectare rates.
- Preserve all source fingerprints and deep immutable output records.

## Non-goals

- No legacy `Zone`/`POI` conversion, runtime topology mode, trip generation,
  renderer, empirical calibration, or external-data learning.
- No zoning fallback and no seed-specific threshold adjustment.

## Acceptance

- Six styles by seeds 17, 29, 41, and 44 pass complete block coverage,
  frontage, industrial buffer, essential-access, POI-type, determinism, and
  import-firewall gates.
- Existing planar and legacy city behavior remains unchanged.
