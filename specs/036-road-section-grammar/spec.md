# Road Section Grammar Spec

## Goal

Replace placeholder lane metadata with a Metroflow-owned, unit-explicit,
deterministic road-section grammar.

## Requirements

- **FR-001:** Every section unit MUST have a typed role and finite positive
  width in meters.
- **FR-002:** Travel lanes MUST have forward/backward direction; non-travel
  units MUST not.
- **FR-003:** Section ends MUST contain at least one travel lane and expose
  directional lane counts and total width.
- **FR-004:** Base profiles require identical sections and offsets.
- **FR-005:** Shift profiles preserve lane/unit layout and limit lateral shift
  using an explicit design standard.
- **FR-006:** Transition profiles change total lane count by exactly one.
- **FR-007:** Ramp profiles change total lane count by exactly one and include a
  channel separator.
- **FR-008:** Equivalent profiles MUST have deterministic SHA-256 fingerprints,
  including signed-zero normalization.
- **FR-009:** Existing `CarriagewayProfile` construction remains compatible.
- **FR-010:** Transition/ramp lane change MUST affect exactly one travel
  direction; the other direction remains unchanged.
- **FR-011:** Transition preserves center offset and ordered non-lane units.
- **FR-012:** Ramp preserves non-channel roadside units and adds/removes exactly
  one channel on the wider/narrower end with the lane change.
- **FR-013:** `fingerprint` is structural and excludes `profile_id` and unused
  design-standard widths; `identity_fingerprint` additionally includes
  `profile_id`.

## Boundaries

- Pure Python/stdlib; no CSUR, Blender, Unity, JAX, Rust, or torch import.
- No lane-level dynamic state or vehicle movement.
- Assignment to generated links is PR37 scope.

## Success

- All interface types have valid and invalid targeted tests.
- Units and failure conditions are explicit.
- Full repository gates pass without changing flow/replay output.

## Compact CCoT

Question: Which road-asset concepts improve Metroflow without importing a game
asset framework?
Evidence: static links need explicit width and transition semantics, while
runtime remains aggregate.
Inference: a small immutable unit grammar is sufficient.
Counterevidence checked: exhaustive asset enumeration would add unused catalog
complexity and licensing risk.
Decision: implement only unit, section-end, and four interface contracts.
Falsifier: rendering or aggregate compilation requires game-prefab semantics.
Next action: assign profiles and compile aggregate link/node metadata.
