# Map gallery for the second external audit

Seventeen renders of the topologies the morphology control table scores, drawn
by `tools/render_audit_maps.py` from the current tree.

**These are not evidence.** Nothing here measures anything. Every number printed
on a map is read back out of
`artifacts/runtime_spine_review/morphology-control-table-v3-20260808.json`, so a
render cannot disagree with the table it illustrates, and a case that table does
not contain refuses to render rather than appear uncaptioned. The claim ledger
forbids presenting image artifacts as scientific validation; this directory
exists so a reviewer can *navigate* to the measurements, not stand in for them.

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

| file | arm | case | envelope verdict | nodes | why it is here |
|---|---|---|---|---|---|
| `growth_fabric_v1--grid_core--s17.svg` | growth_fabric_v1 | grid_core/17 | PASS 7/7 | 1841 | arm under review |
| `growth_fabric_v1--polycentric_tod--s17.svg` | growth_fabric_v1 | polycentric_tod/17 | PASS 7/7 | 2032 | arm under review |
| `growth_fabric_v1--ring_radial--s17.svg` | growth_fabric_v1 | ring_radial/17 | PASS 7/7 | 1882 | arm under review |
| `growth_fabric_v1--river_constrained--s17.svg` | growth_fabric_v1 | river_constrained/17 | PASS 7/7 | 1598 | arm under review |
| `growth_fabric_v1--organic--s17.svg` | growth_fabric_v1 | organic/17 | PASS 7/7 | 1848 | arm under review |
| `growth_fabric_v1--superblock_mixed--s17.svg` | growth_fabric_v1 | superblock_mixed/17 | PASS 7/7 | 1867 | arm under review |
| `growth_fabric_v1--grid_core--s29.svg` | growth_fabric_v1 | grid_core/29 | PASS 7/7 | 1790 | seed spread |
| `growth_fabric_v1--grid_core--s53.svg` | growth_fabric_v1 | grid_core/53 | PASS 7/7 | 1690 | seed spread |
| `standard--polycentric_tod--s17.svg` | standard | polycentric_tod/17 | FAIL `mean_node_degree` | 945 | runtime default, 0/10 |
| `standard--ring_radial--s17.svg` | standard | ring_radial/17 | FAIL `mean_node_degree` | 926 | runtime default, 0/10 |
| `realistic_synthetic_v1--grid_core--s17.svg` | realistic_synthetic_v1 | grid_core/17 | FAIL `mean_node_degree`, `dead_end_share` | 799 | rejected arm, 0/30 |
| `realistic_synthetic_v1--polycentric_tod--s17.svg` | realistic_synthetic_v1 | polycentric_tod/17 | FAIL `mean_node_degree`, `dead_end_share` | 1974 | rejected arm, 0/30 |
| `sidecar_local_fabric--grid_core--s17.svg` | sidecar_local_fabric | grid_core/17 | PASS 7/7 | 522 | partial arm, 15/30 |
| `sidecar_local_fabric--superblock_mixed--s17.svg` | sidecar_local_fabric | superblock_mixed/17 | **PASS 7/7** | 440 | **passes every metric and is not a city** |
| `osm--barcelona.svg` | osm | barcelona.osm | PASS 7/7 | 819 | positive control, 5/5 |
| `osm--chicago.svg` | osm | chicago.osm | PASS 7/7 | 816 | positive control, 5/5 |
| `osm--charlotte.svg` | osm | charlotte.osm | PASS 7/7 | 370 | positive control, 5/5 |

The gallery deliberately includes arms that fail and an arm that passes for the
wrong reasons. A gallery of only the arm under review would be an argument.

## Start here

**`sidecar_local_fabric--superblock_mixed--s17.svg`.** It passes all seven
metrics with 440 nodes and is visibly not a city. That is the standing
counter-example against the metric set itself, and it is the reason
`growth_fabric_v1` scoring 30/30 on those same seven numbers is not by itself an
argument for promotion. If the second audit overturns one thing, this is the
most productive place to aim.

Then compare `growth_fabric_v1--grid_core--s17.svg` against `osm--barcelona.svg`
and `osm--charlotte.svg` at the same caption format. The generated fabric sits
inside the measured density band but in its lower half, which is the open
calibration question below.

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
- Numbers: `artifacts/runtime_spine_review/morphology-control-table-v3-20260808.json`
- OSM fixtures: `artifacts/osm_control/`, © OpenStreetMap contributors, ODbL.
  Derived renders inherit that licence and attribution.
- Standing claim boundaries: `docs/harness/CLAIM_LEDGER.md`
