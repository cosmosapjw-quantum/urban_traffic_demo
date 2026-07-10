# Geometry Artifact Migration

Status: active for artifacts generated after PR35

## Hierarchy Metadata

- `csur_module_signature` became `road_hierarchy_module_signature`.
- `csur_module_alignment_ok` became `road_hierarchy_module_alignment_ok`.

New runtime and static-map artifacts emit only the project-owned names. Old
diagnostic files remain historical snapshots and are not rewritten. Consumers
must treat absence of the new keys in an old artifact as an artifact-version
boundary, not as a failed hierarchy result.

## Geometry Version

`ui_network_geometry_version` now includes the full deterministic road-geometry
fingerprint. A centerline change therefore invalidates UI/static geometry
caches even when node and link counts stay constant.

This migration changes static artifact metadata only. It does not change
traffic replay, flow arrays, or routing costs.
