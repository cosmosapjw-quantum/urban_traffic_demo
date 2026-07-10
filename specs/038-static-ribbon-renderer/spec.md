# Static Ribbon Renderer Spec

## Goal

Render project-owned physical centerlines and road-section widths as a static
diagnostic map without changing runtime topology or simulation authority.

## Requirements

- **FR-001:** Every physical centerline MUST render exactly once regardless of
  its directed-link assignment count.
- **FR-002:** SVG road ribbons MUST follow every centerline point and scale the
  compiled full-section width from meters to display pixels.
- **FR-003:** Median, shoulder, ramp, bridge, and connectivity-repair metadata
  MUST be explicit in the payload and styling.
- **FR-004:** `roads`, `zones`, and `pois` MUST be independently selectable
  diagnostic layers with a fail-closed layer name contract.
- **FR-005:** Directed link metrics MUST remain available in the payload; road
  rendering MUST NOT mutate or replace `RoadNetworkCSR` authority.
- **FR-006:** HTML and JSON outputs MUST preserve geometry/section fingerprints
  and selected routing/agent backend metadata.

## Boundaries

- No browser, image, or network dependency in core tests.
- PNG generation remains an optional development smoke command.
- Visual output is diagnostic only and is not validation evidence.
- No lane-level vehicles, connectors, or signal dynamics.

## Compact CCoT

Question: Why did the prior static map look unlike a credible road map?
Evidence: It rendered every directed link as a duplicate endpoint line and did
not use physical centerline or section-width contracts.
Inference: A physical-road ribbon layer is the smallest architectural fix.
Counterevidence checked: richer lane geometry would exceed aggregate scope.
Decision: render one width-aware path per physical centerline.
Falsifier: visual audit still cannot distinguish hierarchy or curved roads.
Next action: add offline OSM reference import for comparison, not authority.
