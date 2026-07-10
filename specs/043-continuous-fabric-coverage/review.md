# PR43 Review Record

Status: accepted
Date: 2026-07-11

## /review-spec

- Added explicit 24 by 24 local-street cell presence and 12 by 12 local-junction
  proximity contracts.
- Kept Python/NumPy authority, planar sidecar admission, deterministic replay,
  external-data prohibition, and runtime defaults unchanged.
- Implemented style-owned radial, orthogonal, rotated-superblock,
  district-tree, and barrier-aware corridor infill.
- Did not change zone/POI semantics, Rust/JAX/GPU backends, or lane-level state.

## /review-code

Initial findings:

- v2 metrics could be evaluated with non-v2 raster parameters;
- constrained corridors failed open without valid barrier data and unknown
  patterns fell through;
- the first barrier test did not cover the integrated local fabric;
- the junction anti-gaming claim lacked a presence-passing counterexample.

Closure:

- gate v2 requires exact resolution and radius constants;
- unknown patterns and missing barriers fail closed;
- all final corridor local segments are split at barriers, and an independent
  integrated planar test confirms zero local crossings with bridge crossings
  retained;
- a long-line cycle passes cell presence but fails junction proximity.

Independent static re-review closed all four findings.

## /review-drift

Question: Does higher raster presence represent continuous block fabric rather
than merely more long lines?

Evidence: The first wide tree-band draft passed presence but looked like large
X-shaped lines. It was rejected. The final mixed form uses a coarse rotated
grid, polycentric bands are narrower, and gate v2 also requires nearby local
junctions.

Inference: Presence and junction proximity together are a stronger structural
regression contract, but remain synthetic diagnostics rather than realism
validation.

Counterevidence checked: All styles pass topology and PR42 metrics, while the
PNG atlas still shows schematic regularity and long corridor skeletons.

Decision: Accept the narrower structural substrate and open morphology-gated
land-use coupling. Do not promote the planar mode or claim named-city realism.

Falsifier: Zone/POI coupling reveals that raster gains come from unusable or
semantically incoherent street placement.

Next action: PR44 legacy-default, fail-closed morphology-gated zone/POI
placement with replay fingerprint coverage.

## Gates

- focused anti-gaming/barrier tests: `7 passed`
- targeted city suite: `67 passed in 83.02s`
- full repository: `479 passed in 134.19s`
- Ruff and `git diff --check`: passed
- independent review: all findings closed
