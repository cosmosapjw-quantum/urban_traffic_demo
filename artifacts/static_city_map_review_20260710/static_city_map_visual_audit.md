# Static City Map Visual Audit

Label: DIAGNOSTIC / SMOKE REVIEW ARTIFACT, not validation.

## Artifacts

- Full extent HTML: `artifacts/static_city_map_review_20260710/static_city_map_full_extent.html`
- Largest-component HTML: `artifacts/static_city_map_review_20260710/static_city_map_largest_component.html`
- Full page PNG: `artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png`
- Map-only PNG: `artifacts/static_city_map_review_20260710/static_city_map_full_extent_map_only.png`
- Largest-component PNG: `artifacts/static_city_map_review_20260710/static_city_map_largest_component_page.png`
- Manifest: `artifacts/static_city_map_review_20260710/static_city_map_manifest.json`

## Script / Data Provenance

- Entrypoint: `metroflow.sim.init.build_initial_simulation_state` and `metroflow.ui.static_map`
- Scenario seed: `44`
- Config: `population_target=100000`, `active_agent_capacity=64`, `eager_trip_generation=False`
- PNG renderer: system `google-chrome --headless=new`
- Crop tool: ImageMagick `convert`

## Topology Metrics

- Scenario: `synthetic-44`
- Nodes: `1128`
- Links: `5642`
- Zones: `24`
- POIs: `3458`
- Road classes: `arterial=114`, `bridge=8`, `collector=658`, `expressway=32`, `local=4814`, `ramp=16`
- Weak components before repair: `4`
- Component sizes before repair: `1121`, `3`, `3`, `1`
- Connectivity repair links: `6`
- Weak components after repair: `1`
- Component sizes after repair: `1128`

## Image Smoke Metrics

- `static_city_map_full_extent_page.png`: `1280x1120`, `16025` unique colors, nonwhite fraction `0.312464`
- `static_city_map_full_extent_map_only.png`: `1220x766`, `13405` unique colors, nonwhite fraction `0.124470`
- `static_city_map_largest_component_page.png`: `1280x1120`, `16025` unique colors, nonwhite fraction `0.312464`

## Visual Findings

1. The rendered graph is connected after deterministic repair. The artifact still exposes the repaired fringe via red dashed repair links, so the previous disconnected-component failure is not hidden.
2. The largest-component rendering is visually identical to the full extent because repair collapses seed `44` to one weak component. This is expected for the current generator state.
3. Expressway, arterial, collector, local, ramp, bridge, and repair-link styles are all visible in the legend and map.
4. Bridge group labels render and are legible enough for coarse visual review.
5. POI dots remain dense enough to obscure local-road inspection in the urban clusters.
6. Zones are shown as translucent centroid circles, not polygon boundaries. They support orientation only, not zone coverage claims.
7. The static map is useful for topology/fringe/road-class inspection, but not for dynamic traffic, route feasibility, or lane-level correctness.

## Commands Run

```bash
.venv/bin/python -m pytest tests/test_static_city_map.py tests/test_city_connectivity.py -q
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png \
  file://$PWD/artifacts/static_city_map_review_20260710/static_city_map_full_extent.html
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map_review_20260710/static_city_map_largest_component_page.png \
  file://$PWD/artifacts/static_city_map_review_20260710/static_city_map_largest_component.html
convert artifacts/static_city_map_review_20260710/static_city_map_full_extent_page.png \
  -crop 1220x766+30+193 +repage \
  artifacts/static_city_map_review_20260710/static_city_map_full_extent_map_only.png
```

## What This Does Not Show

- No dynamic traffic validation.
- No OD route-feasibility proof beyond weak connectivity.
- No real-world geographic correspondence.
- No lane-level or turn-level audit.
- No GPU/NN/backend performance claim.

## Next Plot Needed

Generate layer-isolated PNGs for roads-only, zones-only, and POIs-only once the next city-map review slice opens. That would make local connectivity and land-use density easier to inspect without POI overplotting.
