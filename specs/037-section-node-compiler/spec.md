# Section And Node Compiler Spec

## Goal

Assign static road-section profiles to generated physical roads and compile
deterministic aggregate node-interface metadata without introducing lane-level
traffic dynamics.

## Requirements

- **FR-001:** Every generated link MUST have one section assignment.
- **FR-002:** Opposite links on one physical road MUST share one full-corridor
  profile and use opposite travel directions.
- **FR-003:** Assignment lane count and capacity MUST equal authoritative
  `RoadLink` aggregate values.
- **FR-004:** Profile selection MUST be deterministic from road class,
  directional lanes, median policy, and roadside policy.
- **FR-005:** Node compilation MUST use oriented centerline tangents and exclude
  immediate U-turns from through continuity.
- **FR-006:** Turn-pocket eligibility, non-through movement count, and signal eligibility
  MUST be deterministic and static.
- **FR-007:** Catalog fingerprints MUST be stable across repeated generation.

## Boundaries

- No mutation of CSR, `LinkState`, `NodeState`, route costs, or capacities.
- No lane-level vehicle state, lane changing, or signal simulation.
- Node interfaces are geometry/reporting metadata and future aggregate-turn
  inputs only.

## Success

- Fixed-seed generated topology has complete section and node catalogs.
- A four-arm fixture identifies two straight-through movements and rejects
  immediate U-turn continuity.
- Full repository gates pass with replay behavior unchanged.

## Compact CCoT

Question: How can road sections affect map realism without changing mesoscopic
authority?
Evidence: PR36 provides static sections and RoadLink already owns aggregate
lanes/capacity.
Inference: compile assignments and validate parity rather than replacing
runtime arrays.
Counterevidence checked: lane connector simulation would violate v1 scope.
Decision: generate static assignment/node catalogs only.
Falsifier: aggregate flow requires lane-resolved state to remain conservative.
Next action: render centerlines and sections as diagnostic ribbons.
