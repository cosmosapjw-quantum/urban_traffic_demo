# Offline OSM Reference Import Spec

## Goal

Import a local OSM XML extract into Metroflow-owned node, link, centerline, and
section contracts for deterministic visual and topology comparison.

## Requirements

- **FR-001:** Parsing MUST use Python standard-library XML only and MUST NOT
  perform network access.
- **FR-002:** Latitude/longitude MUST project deterministically to local meters
  with the projection origin recorded in metadata.
- **FR-003:** Included ways MUST split at endpoints and nodes shared by included
  ways while preserving unshared interior points as centerline geometry.
- **FR-004:** Optional clipping and simplification MUST operate in meter space,
  preserve endpoints, and be deterministic.
- **FR-005:** Supported highway, oneway, lane, speed, bridge/layer, and source
  metadata MUST map through explicit project-owned rules.
- **FR-006:** Missing references, malformed explicit numeric tags, duplicate
  source IDs, or invalid geometry MUST fail closed.
- **FR-007:** Repeated imports MUST produce identical geometry, section, and
  result fingerprints.
- **FR-008:** Source node identity MUST remain authoritative even when distinct
  OSM nodes share coordinates; the exact XML bytes and declared version MUST
  be provenance-bound.

## Boundaries

- Imported OSM is optional reference/development input, not a base dependency.
- No runtime HTTP client, geocoder, tile provider, or OSM package.
- No donor CSUR source, naming grammar, or game-engine assumptions.
- Import does not prove routing realism or validate the synthetic generator.
- Descriptive tags not used by the typed contracts remain bound by the input
  SHA-256 but are not copied into runtime state in this slice.

## Compact CCoT

Question: What reference can falsify generator-shape assumptions without
making external data authoritative at runtime?
Evidence: OSM XML exposes real centerlines and shared-node topology in a stable
offline format.
Inference: a deterministic offline adapter gives a comparable typed surface.
Counterevidence checked: live OSM fetching would violate dependency boundaries.
Decision: parse caller-supplied XML only and keep results outside default init.
Falsifier: normalized reference topology cannot pass endpoint/topology gates.
Next action: compare structural diagnostics in PR40.
