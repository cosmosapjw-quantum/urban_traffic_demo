# Map gallery for the second external audit

Seventeen renders of the topologies the morphology control table scores, drawn
by `tools/render_audit_maps.py` from the current tree.

**These are not evidence.** Nothing here measures anything. Every number printed
on a map is read back out of
`artifacts/runtime_spine_review/morphology-control-table-v4-20260820.json`, so a
render cannot disagree with the table it illustrates, and a case that table does
not contain refuses to render rather than appear uncaptioned. Each record also
stores the exact source-topology fingerprint, and the renderer refuses a current
topology that differs by even one fingerprinted node, link, or road-geometry
field. The claim ledger
forbids presenting image artifacts as scientific validation; this directory
exists so a reviewer can *navigate* to the measurements, not stand in for them.
That table covers legacy, sidecar, realistic-v1, growth-v1, and offline OSM
arms; it does not score or validate `scalable_synthetic_v2`.

The 44 PNGs previously committed were deleted in the same change. They were
rendered by a generator that has since been substantially repaired, so opening
one would have shown a reviewer code that no longer exists.

## Regenerate and verify

```bash
.venv/bin/python tools/render_audit_maps.py --out artifacts/external_audit_2_maps
.venv/bin/python tools/render_audit_maps.py --check   # bytes must reproduce
```

SVG, not screenshots: no browser and no plotting dependency, the geometry is
diffable as text, and a rerun that changes nothing changes nothing.

## What is here

| file | arm | case | why it is here |
|---|---|---|---|
| `growth_fabric_v1--grid_core--s17.svg` | growth_fabric_v1 | grid_core/17 | arm under review |
| `growth_fabric_v1--polycentric_tod--s17.svg` | growth_fabric_v1 | polycentric_tod/17 | arm under review |
| `growth_fabric_v1--ring_radial--s17.svg` | growth_fabric_v1 | ring_radial/17 | arm under review |
| `growth_fabric_v1--river_constrained--s17.svg` | growth_fabric_v1 | river_constrained/17 | arm under review |
| `growth_fabric_v1--organic--s17.svg` | growth_fabric_v1 | organic/17 | arm under review |
| `growth_fabric_v1--superblock_mixed--s17.svg` | growth_fabric_v1 | superblock_mixed/17 | arm under review |
| `growth_fabric_v1--grid_core--s29.svg` | growth_fabric_v1 | grid_core/29 | seed spread |
| `growth_fabric_v1--grid_core--s53.svg` | growth_fabric_v1 | grid_core/53 | seed spread |
| `standard--polycentric_tod--s17.svg` | standard | polycentric_tod/17 | runtime default |
| `standard--ring_radial--s17.svg` | standard | ring_radial/17 | runtime default |
| `realistic_synthetic_v1--grid_core--s17.svg` | realistic_synthetic_v1 | grid_core/17 | rejected comparison arm |
| `realistic_synthetic_v1--polycentric_tod--s17.svg` | realistic_synthetic_v1 | polycentric_tod/17 | rejected comparison arm |
| `sidecar_local_fabric--grid_core--s17.svg` | sidecar_local_fabric | grid_core/17 | partial comparison arm |
| `sidecar_local_fabric--superblock_mixed--s17.svg` | sidecar_local_fabric | superblock_mixed/17 | standing metric counter-example |
| `osm--barcelona.svg` | osm | barcelona.osm | positive control |
| `osm--chicago.svg` | osm | chicago.osm | positive control |
| `osm--charlotte.svg` | osm | charlotte.osm | positive control |

The gallery deliberately includes arms that fail and an arm that passes for the
wrong reasons. A gallery of only the arm under review would be an argument.

## Start here

**`sidecar_local_fabric--superblock_mixed--s17.svg`.** Its v4-derived caption
passes every metric while the rendering is visibly not a city. That is the
standing counter-example against treating the metric set as promotion
authority. If the second audit overturns one thing, this is the most productive
place to aim.

Then compare `growth_fabric_v1--grid_core--s17.svg` against `osm--barcelona.svg`
and `osm--charlotte.svg` at the same caption format. Use those v4-derived
captions, rather than copied README values, for the open calibration comparison.

## What these renders cannot show you

- **No traffic quantity has been measured at all.** Seven morphology metrics say
  nothing about whether these networks carry traffic sensibly. That gate is
  designed and unbuilt.
- **`spacing_scale = 3.0` is a constant fitted to a bug.** It was calibrated
  while the branch-spacing units were inconsistent; repairing them voided its
  authority, and it has not been re-derived.
- **Nothing measures block size**, which is the observable that would separate
  correct calibration from under-seeding.
- Grade separation, land use, and signals are not drawn. Line weight encodes road
  class only.

## Provenance

- Renderer: `tools/render_audit_maps.py`, tested by `tests/test_audit_map_render.py`
- Numbers and exact source identity:
  `artifacts/runtime_spine_review/morphology-control-table-v4-20260820.json`
- OSM fixtures: `artifacts/osm_control/`, © OpenStreetMap contributors, ODbL.
  Derived renders inherit that licence and attribution.
- Standing claim boundaries: `docs/harness/CLAIM_LEDGER.md`
