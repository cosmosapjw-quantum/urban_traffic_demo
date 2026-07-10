# PR42 Review Record

Status: accepted
Date: 2026-07-11

## /review-spec

- Implemented physical-road density, length-weighted block continuity,
  connector/local ratio, degree mix, weak-component count, and precisely named
  district quadrant presence.
- Preserved Python/NumPy authority and avoided Rust, JAX, torch, CUDA, external
  data, named-city fitting, runtime-default changes, and zone/POI semantics.
- Added a three-seed report and a wider six-style/four-seed fail-closed gate
  regression matrix.

## /review-code

Initial findings:

- non-finite metrics could pass comparisons;
- connectivity was claimed without component evidence;
- river dead-end thresholds were duplicated;
- quadrant presence was overnamed as coverage;
- fail-closed seed/style coverage was too narrow;
- artifact IO lived in the city-domain metric module.

Closure:

- immutable metric validation now rejects non-finite, out-of-range, and
  inconsistent values;
- weak components are measured and gated;
- thresholds have one versioned source;
- the public metric name is `district_quadrant_presence_share`;
- all six styles are covered across seeds 5, 17, 29, and 41;
- report orchestration and IO moved to `metroflow.ui`.

Independent re-review found no remaining defect in the reviewed findings.

## /review-drift

Question: Does passing PR42 authorize morphology-aware land-use placement?

Evidence: Local intersection and continuity metrics improve across three
deterministic seeds, but the regenerated contact sheet still shows precinct
islands and bare inter-district links.

Inference: The v1 gate is valid only for weak connectivity, block continuity,
density, and intersection mix. It does not establish citywide fabric coverage.

Counterevidence checked: Sampled OD reachability and convex-hull density pass,
but neither measures spatial gaps between district envelopes.

Decision: Accept PR42 with a narrow claim. Insert continuous-fabric PR43 before
zone/POI coupling.

Falsifier: A global cell-coverage probe shows that the visible gaps are only a
renderer artifact.

Next action: Implement a decision-changing global coverage probe and
style-aware inter-district infill.

## Gates

- targeted morphology/static suite: `49 passed`
- full repository: `472 passed in 125.08s`
- Ruff: passed
- `git diff --check`: passed
- visual artifact: `artifacts/city_morphology_atlas_20260711/contact_sheet.png`
