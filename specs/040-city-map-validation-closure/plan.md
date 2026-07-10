# Implementation Plan: City Map Validation Closure

- Add deterministic endpoint-topology planarization with old-to-new link mapping.
- Add explicit planar sidecar mode and gate its finalization without changing the default.
- Add city-map validation report for topology, geometry, sections, OD, and provenance.
- Add deterministic/replay regression coverage across reviewed seeds.
- Regenerate full, focused, roads, zones, and POI diagnostics and inspect PNGs.
- Update ledger, roadmap, state docs, and final review record.
