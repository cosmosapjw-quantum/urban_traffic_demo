# Research: City Map Source Boundary

## Decision

Use CSUR only as a conceptual reference for road cross-sections and segment
interfaces. Do not copy or vendor its implementation.

## Rationale

- The reviewed upstream snapshot is GPL-3.0.
- Its README identifies it as an asset-generation framework and states that
  the game places, stretches, and bends generated straight segments.
- Metroflow needs a centerline/topology compiler in addition to a road-section
  grammar.

## Alternatives Considered

- **Direct vendoring:** rejected pending a repository licensing decision.
- **Optional runtime dependency:** rejected because external donor dependency
  violates the self-contained runtime requirement.
- **Ignore the research:** rejected because the neutral cross-section model is
  useful when restated under Metroflow-owned contracts.
