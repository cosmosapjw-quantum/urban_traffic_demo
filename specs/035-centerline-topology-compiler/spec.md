# Centerline Topology Compiler Spec

## Goal

Attach complete typed centerline geometry to generated topologies, expose the
existing organic sidecar through explicit configuration, and remove misleading
legacy compatibility metadata.

## Requirements

- **FR-001:** Every generated directed link MUST have one geometry assignment.
- **FR-002:** Opposite directions of one physical road MUST share a stable
  `physical_road_id` and centerline.
- **FR-003:** Finalization MUST repair weak connectivity before runtime
  acceptance and record before/after metadata.
- **FR-004:** `CityGenerationConfig.topology_mode` MUST accept only `standard`
  and `sidecar_local_fabric`; default remains `standard`.
- **FR-005:** Static geometry fingerprint and selected topology mode MUST be
  preserved in initialized state metadata and geometry version.
- **FR-006:** Legacy `csur_module_*` outputs MUST be replaced by project-owned
  `road_hierarchy_module_*` names and documented as an artifact migration.
- **FR-007:** Centerline endpoints MUST match directed link endpoints within an
  explicit meter tolerance or finalization fails.
- **FR-008:** Same-layer proper centerline crossings MUST be counted in a
  deterministic diagnostic audit; PR35 MUST NOT present the count as a
  planar-topology validation result.

## Contract Impact

- `RoadLink` gains optional nonnegative `physical_road_id` static metadata.
- `PreviewCityTopology` gains optional `road_geometry` static metadata.
- No traffic array, scheduler, route, or flow semantics change.
- Geometry fingerprint invalidates UI/static geometry consumers when geometry
  changes.

## Acceptance

- Standard and sidecar fixed-seed outputs are deterministic and connected.
- Geometry assignment count equals link count.
- Sidecar remains opt-in.
- Legacy metadata names are absent from new runtime artifacts.
- Repeated fixed-seed generation reproduces repair IDs, topology, and geometry
  fingerprints for both modes.
- Targeted and full gates pass.

## Compact CCoT

Question: Can richer generated centerlines enter runtime without changing its
traffic authority?
Evidence: PR34 isolates geometry, while initialization already has a static
geometry-version boundary.
Inference: Finalization can attach geometry and use its fingerprint for static
cache invalidation.
Counterevidence checked: The sidecar is disconnected before repair and cannot
be made default safely.
Decision: repair+gate all modes, expose sidecar explicitly, retain standard
default.
Falsifier: sidecar cannot pass topology, zoning, and route initialization.
Next action: add project-owned road-section profiles.
