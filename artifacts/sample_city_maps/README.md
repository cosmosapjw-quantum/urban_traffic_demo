# MetroFlow Urban Morphology Sample Maps Gallery

> **PROVENANCE**: These artifacts are generated exclusively by the
> `scalable_synthetic_v2` pipeline via `tools/render_morphology_gallery.py`.
> The gallery manifest (`gallery_manifest.json`) records the exact
> `topology_mode`, network/block/compiled/authority fingerprints, and
> node/link counts for each rendered map.

> **NOTE**: An earlier version of this gallery incorrectly rendered maps
> using the `realistic_synthetic_v1` (legacy) generator while labeling
> them as "scalable morphology" samples. That provenance error has been
> corrected. Legacy gallery images have been moved to
> `artifacts/legacy_realistic_v1_gallery/`.

Each map visualizes:
- **Road Hierarchy**: Expressways (blue), Arterials (orange), Collectors (teal), Local roads (gray), Ramps (purple), Bridge spans (cyan).
- **Physical Road Structures**: Width-aware ribbon rendering.
- **Topological Features**: Waterway boundaries and multi-span bridges (`river_constrained`), radial corridors (`ring_radial`), orthogonal grids (`grid_core`), transit centers (`polycentric_tod`), superblock perimeters (`superblock_mixed`), and organic networks (`organic`).

> **CAUTION**: All 6 morphology archetypes currently share the same
> underlying adaptive rectilinear lattice generator. Visual differences
> are driven by label-dependent noise and minor parametric variation,
> not distinct spatial grammars. Morphological differentiation is a
> known `HOLD/FAIL` per the external audit.

---

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python tools/render_morphology_gallery.py --out artifacts/sample_city_maps
```

HTML-only (no Chrome/Chromium screenshot):

```bash
PYTHONPATH=src .venv/bin/python tools/render_morphology_gallery.py --html-only
```
