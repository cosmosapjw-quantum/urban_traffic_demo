# Static City Map Visual Audit

Label: SMOKE / DIAGNOSTIC, not validation.

## Artifacts

- `artifacts/static_city_map/static_city_map_page.png`
- `artifacts/static_city_map/static_city_map_map_only.png`
- `artifacts/static_city_map/static_city_map_largest_component.png`
- Source HTML: `artifacts/static_city_map/static_city_map.html`
- Focused HTML: `artifacts/static_city_map/static_city_map_largest_component.html`
- Manifest: `artifacts/static_city_map/static_city_map.json`

## Generation

PNG conversion used system Chrome headless rendering from the committed standalone
HTML/SVG artifact:

```bash
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map/static_city_map_page.png \
  file://$PWD/artifacts/static_city_map/static_city_map.html
google-chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --run-all-compositor-stages-before-draw --virtual-time-budget=1000 \
  --window-size=1280,1120 \
  --screenshot=artifacts/static_city_map/static_city_map_largest_component.png \
  file://$PWD/artifacts/static_city_map/static_city_map_largest_component.html
convert artifacts/static_city_map/static_city_map_page.png \
  -crop 1220x766+30+193 +repage \
  artifacts/static_city_map/static_city_map_map_only.png
```

## Visual Findings

1. The previous disconnected edge fragments are now explicitly stitched into the
   main component. The renderer marks those `6` bidirectional repair links in
   red dashed styling, and the generated graph reports one weak component of
   size `1128`.

2. Before repair, the same seed-44 graph had 4 weak components with sizes
   `1121`, `3`, `3`, and `1`. This remains recorded in artifact metadata so
   downstream reviewers can see that the generator repaired a real topology
   defect rather than merely hiding it in visualization.

3. The road hierarchy is now complete in the legend for the rendered classes:
   expressway, arterial, collector, local, ramp, bridge, and repair-link.

4. POI dots dominate dense districts and obscure local-road inspection. The
   artifact is useful for spotting district massing, but dense POI layers make it
   hard to audit local connectivity and turn structure in hotspots.

5. Zones are centroid circles, not boundaries. They help locate coarse land-use
   centers, but they cannot support claims about zone coverage, adjacency, or
   service areas.

6. Large whitespace is reduced as an interpretability problem but not eliminated:
   the full-extent artifact intentionally keeps repaired fringe fragments visible.
   The largest-component-focused artifact is retained as the review-oriented view.

7. Bridge links are easier to locate because bridge group labels are rendered,
   but this still is not a bottleneck validation surface.

## Topology Metrics

- Scenario: `synthetic-44`
- Nodes: `1128`
- Links: `5642`
- Zones: `24`
- POIs: `3458`
- Road classes: `arterial=114`, `bridge=8`, `collector=658`,
  `expressway=32`, `local=4814`, `ramp=16`
- Weak components before repair: `4`
- Component sizes before repair: `1121`, `3`, `3`, `1`
- Connectivity repair links: `6`
- Weak components after repair: `1`
- Component sizes after repair: `1128`

## Recommended Fix Order

1. Add regression coverage over a seed batch so this repair does not only cover
   seed 44.
2. Add layer toggles or alternate PNG outputs for roads-only, POI-only, and
   zones-only review.
3. Add quantitative route feasibility sampling over OD pairs after repair.
4. Add bridge bottleneck and incident overlays for traffic-specific review.

## What This Does Not Show

- No dynamic traffic validation.
- No route feasibility guarantee beyond the simple component metric.
- No real-world geographic correspondence.
- No microscopic lane or turn-level audit.
