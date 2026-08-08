# Urban Morphology Diversity

Status: implemented substrate; diagnostic evidence only

## Purpose

Metroflow no longer treats a hub-and-spoke network as the generic city form.
The explicit sidecar generator supports six project-owned grammars:

- `ring_radial`: legacy monocentric control
- `grid_core`: one dominant orthogonal grid
- `polycentric_tod`: several comparable centers with mesh links
- `river_constrained`: longitudinal banks with limited transverse crossings
- `superblock_mixed`: locally ordered grids with competing orientations
- `organic`: irregular accretion, district loops, and non-orthogonal links

`CityGenerationConfig.morphology_style_id="auto"` preserves the historical
scenario default. Explicit styles are intended for review and experiments.

## Literature And Data Boundary

The metric method and reference values come from Boeing (2019), *Urban spatial
order: street network orientation, configuration, and entropy*, Applied Network
Science 4:67, <https://doi.org/10.1007/s41109-019-0189-1>. The study compares
100 OpenStreetMap city networks using orientation entropy/order, median segment
length, circuity, average node degree, dead-end share, and four-way share.

Additional structural interpretation is informed by:

- Strano et al. (2013), primal street-network geometry and city-family
  comparison, <https://doi.org/10.1068/b38216>.
- Lee et al. (2017), route morphology and the mono/polycentric continuum,
  <https://doi.org/10.1038/s41467-017-02374-7>.

The observed values in `morphology_reference.py` are reference-only. They are
not training data, calibration objectives, or evidence that a generated map
replicates a named city. They are also hand-transcribed literals, not values
this repo can re-derive: **three** of the eight reference cities have a committed
extract, and they do not agree with the table uniformly. Charlotte
(`orientation_order` 0.002 in the corpus vs 0.167 measured) and Seoul
(0.009 vs 0.412) differ by two orders of magnitude, while **Chicago agrees
closely** (0.899 vs 0.938).

An earlier version of this paragraph said "only two ... and both disagree",
which was wrong on both counts. The pattern that actually holds is more
informative than the one it asserted: a core bounding box resembles the whole
municipality when the city is a uniform grid, and stops resembling it when the
city is sprawling or organic. So the extract-vs-corpus gap is a property of the
morphology being sampled, not a constant offset that could be corrected for.

Raw OSM extracts **are** committed, under `artifacts/osm_control/` — this
paragraph previously said they were not. OpenStreetMap data is ODbL, so the
extracts and anything derived from them carry the attribution recorded in
`artifacts/osm_control/README.md`. The runtime still fetches nothing: the
offline XML importer reads local bytes only (spec 039 FR-001).

## Diagnostic Contract

`compute_street_network_morphometrics` operates on physical centerlines rather
than counting both directed links. It follows the paper's 36 shifted bearing
bins and orientation-order formula and also reports topology/connectivity
metrics. Generated topology metadata records the result as
`diagnostic_not_city_replication`.

The comparison bundle is generated with:

```bash
.venv/bin/python -m metroflow.ui.morphology_atlas \
  --output-dir artifacts/city_morphology_atlas_20260710 \
  --seed 17
```

The explicit planar atlas passes weak-connectivity, same-layer intersection,
section, node-interface, and sampled-OD gates. These gates establish graph
integrity, not urban realism.

Generated per-style HTML files are reproducible local outputs and are ignored by
Git because the radial payload alone is tens of megabytes. Version control keeps
the compact metric manifest, PNGs, contact sheet, and adversarial visual audit.

## Visual Audit

The atlas demonstrates material macro-structure separation: grid, mixed-grid,
polycentric mesh, constrained corridor, organic, and radial forms are visually
and morphometrically distinct. It also exposes unresolved weaknesses:

- local street fabric does not yet fill every district continuously;
- several connector roads remain too long relative to block-scale streets;
- `polycentric_tod` and `superblock_mixed` overproduce four-way intersections;
- `river_constrained` overproduces dead ends;
- the organic grammar still has sparse limbs despite added district loops;
- zoning and POI placement do not yet respond strongly enough to each grammar.

PR42 must therefore add block-continuity, intersection-mix, street-density, and
connector-length distribution gates before any style becomes a realism claim or
runtime default candidate.

## Claim Audit

| Claim | Status | Evidence | Risk | Required fix |
|---|---|---|---|---|
| Six deterministic morphology grammars compile | IMPLEMENTED | tests and atlas manifest | Low | Maintain parity gates |
| Explicit planar variants satisfy graph integrity gates | VALIDATED | multi-style planar tests | Low | Keep seed matrix coverage |
| Generated styles have distinct morphometric signatures | VALIDATED | deterministic diversity test | Medium | Expand to multi-seed distribution |
| Generated maps reproduce real named cities | FORBIDDEN | none | High | Never infer from nearest metric values |
| Current maps are morphologically realistic | PROPOSED | visual audit shows gaps | High | Complete PR42 quality-envelope work |
