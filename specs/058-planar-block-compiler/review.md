# PR58 Review Record

Status: approved
Date: 2026-07-13

## /review-spec

Finding: the initial test covered all six styles but only one seed, below the
controlling 6-style by 4-seed regression contract.

Fix: expanded the frozen geometry, block-area, frontage, and provenance gate
to seeds 17, 29, 41, and 44. All 24 map cases pass.

## /review-code

Finding loop 1: `CityBlockCatalog` trusted caller-supplied aggregate metrics,
and `CityBlock.centroid_m` used a vertex mean that may lie outside a concave
block.

Fix: catalog construction now recomputes graph IDs, intersections, segment
statistics, block statistics, and frontage from geometry. Blocks validate
simple geometry and use an area-weighted polygon centroid.

Finding loop 2: strengthened simple-polygon validation exposed articulation
face walks and unsplit node-on-segment T-junctions. The accepted endpoint
planarizer covers proper crossings, not endpoint touches.

Fix: added deterministic same-layer T-junction splitting with a bounded
spatial index, short-fragment contraction, spur pruning, and articulation
cycle decomposition before block construction. No findings remain.

## /review-drift

Question: Do extracted blocks prove the street fabric forms usable bounded
urban space rather than only increasing line density?

Evidence: six morphology styles across seeds 17, 29, 41, and 44 produce simple
bounded faces with zero residual proper intersections, zero sub-10m segment
share after cleanup, complete source-street frontage, and frozen block-area
envelopes. The full repository gate remains green.

Inference: the output is a topology-bearing block authority suitable for
block-coupled land use. It is not merely a denser or more attractive drawing.

Counterevidence checked: repeated vertices, self-touching polygons, false
metadata, T-junctions, articulation vertices, optional accelerator imports,
single-seed collapse, and legacy regression.

Decision: approve PR58. Move to land use and POIs; do not continue street
shape tuning without a PR59 contract failure.

Falsifier: residual crossings, exterior-face leakage, non-simple polygons,
threshold failure, false aggregate metrics, or missing street frontage.

Next action: implement block-based land use and POI coupling in PR59. Recheck
module extraction before PR60 rather than adding runtime responsibilities to
the compiler module.

## Gates

- targeted: `29 passed in 60.63s`
- full repository: `691 passed in 360.72s`
- Ruff and diff check: passed
