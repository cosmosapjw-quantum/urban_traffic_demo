# Implementation Plan: Offline OSM Reference Import

- Define immutable import config and result contracts with explicit units.
- Parse local OSM XML nodes/ways and deterministic project-owned tag mappings.
- Project, split shared intersections, clip, simplify, and compile typed output.
- Add malformed-input, one-way, deterministic, and no-network tests.
- Document reference-only claim boundary and review provenance.
