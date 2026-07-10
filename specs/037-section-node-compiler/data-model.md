# Data Model: Section And Node Compilation

- `LinkSectionAssignment`: link, profile, direction, aggregate lane/capacity,
  full section width.
- `RoadSectionCatalog`: unique profiles and complete assignments.
- `CompiledNodeInterface`: incoming/outgoing links, through pairs, turn-pocket
  inputs, non-through movement count, signal eligibility.
- `NodeInterfaceCatalog`: deterministic node interfaces and fingerprint.
