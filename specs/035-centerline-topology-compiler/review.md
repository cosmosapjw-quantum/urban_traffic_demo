# PR35 Review Record

## Review Loop 1

- Found missing endpoint/intersection scope, physical-ID collision risk,
  physical-ID reuse ambiguity, and insufficient deterministic repeats.
- Fixed repair ID allocation, made physical IDs authoritative, added endpoint
  anchoring validation, added grid-indexed crossing diagnostics, and repeated
  both standard and sidecar fixed-seed generation.

## Review Loop 2

- Result: approved.

## Validation

- Focused integration review: `34 passed`.
- Full repository: `372 passed`.
- Ruff: passed.
- `git diff --check`: passed.
- Standard seed 44: `1128` nodes, `5642` directed links, `6` repair links.
- Sidecar seed 44: `1040` nodes, `3098` directed links, `2` repair links.
- Both repeated fingerprints matched.
- Review subagents: closed; zero intentionally open.

## Numerical And Replay Impact

Static centerline length, endpoint anchoring, crossing diagnostics, and geometry
fingerprints are new. Flow stocks, capacities, routing costs, and scheduler
order are unchanged. Geometry fingerprint changes intentionally invalidate UI
geometry caches. Sidecar mode is opt-in; standard remains the default.

Interior crossing counts are diagnostic only and are not topology validation.
