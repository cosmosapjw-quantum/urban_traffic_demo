# MetroFlow Urban Morphology Sample Maps Gallery

> **PROVENANCE & SSOT POLICY**:
> - **SSOT (Single Source of Truth)**: Standalone, self-contained SVG vector maps (`map_{style_id}.svg`) and cryptographic manifest (`gallery_manifest.json`).
> - **Visual Previews**: High-resolution PNGs (`map_{style_id}.png`).
> - **Zero-HTML Architecture**: Rendered directly via `render_static_city_map_svg()` without intermediate HTML wrapper boilerplate or headless browser page dependencies.
> - The gallery manifest records exact `topology_mode`, scale specification, schema versions, stage fingerprints (`network`, `blocks`, `compiled`, `static_authority`, `zoning_placement`, `city_map`), and `svg_sha256` for each morphology.

> **NOTE**: An earlier version of this gallery incorrectly rendered maps
> using the `realistic_synthetic_v1` (legacy) generator while labeling
> them as "scalable morphology" samples. That provenance error has been
> corrected. Legacy gallery images have been moved to
> `artifacts/legacy_realistic_v1_gallery/`.

Each map visualizes:
- **Road Hierarchy**: Expressways (blue), Arterials (orange), Collectors (teal), Local roads (gray), Ramps (purple), Bridge spans (cyan).
- **Physical Road Structures**: Width-aware ribbon rendering.
- **Topological Features**: Waterway boundaries and multi-span bridges (`river_constrained`), radial corridors (`ring_radial`), orthogonal grids (`grid_core`), transit centers (`polycentric_tod`), superblock perimeters (`superblock_mixed`), and organic networks (`organic`).

> **CLAIM BOUNDARY**: The scalable styles now expose distinct structural
> grammars: concentric ring/radial roads, two-dimensional polycentric anchors,
> explicit superblock macrofaces, bounded curvilinear organic connectors, and
> river bridge groups. The gallery is implementation and diagnostic evidence
> for those differences only. It is not named-city calibration, empirical
> morphology validation, or traffic-realism evidence.

## Plot summary

Plot category: **DIAGNOSTIC**.

## Quantity plotted

Physical road centerlines and hierarchy, plus generated zone/POI overlays, for
the six fixed seed-17 scalable morphology cases at 100,000 population and
25 km².

## Script / data provenance

`tools/render_morphology_gallery.py` builds every map through
`scalable_synthetic_v2`. `gallery_manifest.json` binds the fixed input, every
city-authority fingerprint, and both SVG and PNG SHA-256 digests.

## Interpretation

The gallery makes the implemented grammar differences inspectable: orbitals and
radials, multiple spatial centers, superblock macrofaces, curvilinear organic
connectors, and river bridge groups are visible rather than label-only changes.

## What this plot does not show

It does not compare the generated distributions with real cities or validate
traffic, demand, accessibility, land use, or requested-population realization.

## Next plot needed

A fixed-corpus generated-versus-OSM comparison of block-area, intersection-type,
and orientation distributions, after the realistic growth path adopts the new
spatial mechanisms.

---

## Reproduction & Verification

Generate complete SVG + PNG gallery:
```bash
PYTHONPATH=.:src .venv/bin/python tools/render_morphology_gallery.py --out artifacts/sample_city_maps
```

SVG-only (fast, zero browser dependency):
```bash
PYTHONPATH=.:src .venv/bin/python tools/render_morphology_gallery.py --svg-only
```

Verify artifacts against manifest:
```bash
PYTHONPATH=.:src .venv/bin/python tools/render_morphology_gallery.py --check
```
