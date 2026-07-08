# Static City Map Visual Audit

Label: SMOKE / DIAGNOSTIC, not validation.

## Artifacts

- `artifacts/static_city_map/static_city_map_page.png`
- `artifacts/static_city_map/static_city_map_map_only.png`
- Source HTML: `artifacts/static_city_map/static_city_map.html`
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
convert artifacts/static_city_map/static_city_map_page.png \
  -crop 1220x766+30+193 +repage \
  artifacts/static_city_map/static_city_map_map_only.png
```

## Visual Findings

1. Disconnected edge fragments are visible and confirmed by topology metrics.
   The seed-44 graph has 4 weak components: sizes `1121`, `3`, `3`, and `1`.
   This is the highest-priority generator issue because routing/replay over the
   full city can silently inherit no-route pockets unless connectivity gates
   reject or explicitly mark them.

2. The road hierarchy is legible at macro scale but not complete in the legend.
   Expressway, arterial, collector, local, and bridge are shown, but `ramp` is
   present in the data (`16` links) and missing from the legend.

3. POI dots dominate dense districts and obscure local-road inspection. The
   artifact is useful for spotting district massing, but dense POI layers make it
   hard to audit local connectivity and turn structure in hotspots.

4. Zones are centroid circles, not boundaries. They help locate coarse land-use
   centers, but they cannot support claims about zone coverage, adjacency, or
   service areas.

5. Large whitespace is caused by bounds including outlier/disconnected fragments.
   This wastes visual resolution and reduces readability of the main component.

6. Bridge links are too hard to audit as bottlenecks. There are `8` bridge links,
   but the view lacks bridge group labels, crossing names, or a separate
   bottleneck overlay.

## Topology Metrics

- Scenario: `synthetic-44`
- Nodes: `1128`
- Links: `5636`
- Zones: `24`
- POIs: `3458`
- Road classes: `arterial=114`, `bridge=8`, `collector=652`,
  `expressway=32`, `local=4814`, `ramp=16`
- Weak components: `4`
- Component sizes: `1121`, `3`, `3`, `1`
- Leaf nodes: `58`
- Directed zero-out nodes: `1`
- Directed zero-in nodes: `1`

## Recommended Fix Order

1. Add a city-topology connectivity gate before runtime/replay acceptance:
   fail closed by default, or explicitly classify isolated service islands.
2. Add component coloring or component outline to the static map renderer.
3. Add layer toggles or alternate PNG outputs for roads-only, POI-only, and
   zones-only review.
4. Add ramp, POI, zone, and bridge-group legends.
5. Add optional crop-to-largest-component rendering for review readability while
   preserving a full-extent diagnostic artifact.

## What This Does Not Show

- No dynamic traffic validation.
- No route feasibility guarantee beyond the simple component metric.
- No real-world geographic correspondence.
- No microscopic lane or turn-level audit.
