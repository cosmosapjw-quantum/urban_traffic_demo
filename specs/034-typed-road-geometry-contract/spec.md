# Typed Road Geometry Contract Spec

## Goal

Represent static road centerlines independently from directed runtime links so
rendering and future topology compilers can use curves without changing
link-level traffic authority.

## Requirements

- **FR-001:** Centerline points MUST use finite `(x_m, y_m)` meter coordinates.
- **FR-002:** Consecutive points MUST be distinct and each centerline MUST have
  at least two points.
- **FR-003:** Directed links MUST reference centerlines through explicit
  assignments with orientation and lateral offset.
- **FR-004:** Catalog identifiers and link assignments MUST be unique and all
  references MUST resolve.
- **FR-005:** Equivalent inputs MUST produce the same SHA-256 fingerprint
  regardless of input tuple ordering or signed-zero representation.
- **FR-006:** A baseline adapter MUST convert endpoint-only generated links
  without changing nodes, links, capacities, or runtime arrays.
- **FR-007:** Endpoint adaptation MUST reject parallel multiplicities when no
  explicit physical corridor discriminator exists.

## Public Contract

- Authority: `metroflow.map.road_geometry`.
- Failure: invalid geometry or references raise `ValueError`.
- Units: points and lateral offsets are meters; layer is dimensionless.
- Replay/cache: geometry fingerprints may become static cache keys; runtime
  replay is otherwise unchanged in PR34.

## Success Criteria

- Bidirectional links share one physical centerline and recover opposite point
  order through assignments.
- Invalid coordinates, duplicates, and missing references fail closed.
- Targeted tests and full repository gates pass without JAX/Rust imports.

## Out Of Scope

- Intersection splitting, OSM import, road sections, node connectors, ribbons,
  lane-level state, GPU/Rust acceleration.

## Compact CCoT

Question: What contract separates realistic geometry from runtime topology?
Evidence: `RoadLink` stores endpoints only and static rendering draws one line.
Inference: A typed immutable geometry catalog can enrich presentation without
changing flow/routing arrays.
Counterevidence checked: Storing points directly on every directed link would
duplicate bidirectional geometry and couple CSR authority to rendering.
Decision: Use shared centerlines plus directed assignments.
Falsifier: Integration requires per-link geometry mutation during simulation.
Next action: compile generated topology into canonical centerlines.
