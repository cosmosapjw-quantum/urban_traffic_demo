# City Map Validation Closure Spec

## Goal

Promote one generated-city path to a fail-closed runtime authority with planar
same-layer topology, deterministic geometry/section contracts, reachable ODs,
and replay-compatible initialization.

## Requirements

- **FR-001:** Existing `standard` runtime default MUST remain stable. Reviewed
  planar output MUST require explicit `sidecar_local_fabric_planar` selection
  until its initialization cost and route-ID compatibility pass separate gates.
- **FR-002:** Same-layer proper centerline crossings on the runtime path MUST be
  compiled into shared graph nodes before acceptance.
- **FR-003:** Planarization MUST preserve directed class, speed, lane, capacity,
  bridge, blockability, and connectivity-repair provenance.
- **FR-004:** Runtime acceptance MUST fail closed on weak disconnection,
  endpoint-anchor drift, remaining proper crossings, incomplete geometry or
  section assignments, fingerprint mismatch, or sampled unreachable OD pairs.
- **FR-005:** Fixed-seed generation and validation metrics MUST be deterministic.
- **FR-006:** Replay of independently initialized equivalent states MUST preserve
  boundaries, final flow arrays, cache fingerprints, telemetry, and RNG state.
- **FR-007:** Final HTML/PNG map bundles MUST expose isolated layers and carry a
  diagnostic-only manifest and visual audit.

## Boundaries

- No lane-level state or microscopic motion.
- No silent planarization of bridge/different-layer crossings.
- No claim that visual smoke or sampled OD checks establish real-world validity.
- OSM reference import remains optional and is not mixed into synthetic runtime.

## Compact CCoT

Question: Can the new renderer and typed contracts close city-map acceptance?
Evidence: standard seed 44 still has 16,672 proper same-layer non-node crossings;
sidecar local fabric has fewer but still nonzero crossings.
Inference: a planar compiler is required; metadata-only validation is false closure.
Counterevidence checked: planarizing legacy standard would multiply graph size
without improving its dominant outer scaffold.
Decision: expose a fail-closed planar sidecar mode without default promotion.
Falsifier: planarized sidecar breaks replay or capacity parity; default promotion
also requires a separate runtime-budget and route-contract decision.
Next action: regenerate final review artifacts and record residual morphology defects.
