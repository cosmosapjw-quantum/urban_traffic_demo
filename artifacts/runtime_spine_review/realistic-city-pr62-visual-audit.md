# PR62 Realistic City Contact-Sheet Adversarial Audit

Status: diagnostic visual review only
Date: 2026-07-13
Artifact: `realistic-city-pr62-plausibility.png`

## Scope

The contact sheet renders the same seed-17 records used by the 30-map audit.
Each style exposes terrain, pre-compiler roads, bounded blocks, block land use,
and compiled runtime topology. The image is not validation evidence.

## Findings

1. **The local fabric is a triangular lattice across nominally different styles.**
   `ring_radial`, `grid_core`, `polycentric_tod`, `superblock_mixed`, and
   `organic` all contain dense repeated diagonals. `grid_core` is not primarily
   orthogonal and `organic` is not visibly accretive. The runtime layer confirms
   that this is compiled topology, not a renderer artifact.

2. **Blocks are overwhelmingly repeated congruent units.** The seed-17 dominant
   2,500 m2 block-area bin share ranges from about 0.78 to 0.94 for five styles
   and remains 0.86 for organic. This matches the visible field of repeated
   triangular blocks and contradicts the intended mixed functional fabric.

3. **Street hierarchy is visually and numerically weak.** Local streets account
   for 95-98 percent of physical length, collector length share is zero in every
   representative style, and the sparse arterial/expressway skeleton appears
   superimposed on rather than generative of the local network.

4. **The over-connectivity is real topology, not a degree-accounting bug.** An
   independent `grid_core` seed-17 calculation found 799 nodes, 2,147 undirected
   physical edges, mean degree 5.374, and 528 degree-six nodes. Only 29 extra
   parallel edges were present. The empirical mean-degree and dead-end failures
   therefore reflect the triangular mesh.

5. **River response is present but schematic.** `river_constrained` clearly
   preserves the water barrier and crossings, but each bank remains a regular
   lattice precinct. This is a useful barrier contract, not a realistic river
   city morphology.

6. **Land use follows smooth center-distance bands over rasterized blocks.** The
   polycentric and river variants show different center placement, but most
   boundaries are stepped rings and strips rather than parcel/frontage-led
   transitions. This is functional synthetic allocation, not urban land-use
   validation.

7. **Terrain variety is weak outside the river style.** Five representative
   terrains use nearly the same diffuse sinusoidal elevation field and show
   little visible street deflection. The river mask changes topology, while
   slope/elevation mostly changes shading.

8. **The contact sheet itself renders coherently.** All five layers are nonblank,
   aligned to a common extent, and the runtime graph corresponds to the road and
   block layers. No visual overlap or cropping defect explains the morphology
   findings.

## Numeric Closure

- canonical matrix: 6 styles x 5 seeds = 30 maps;
- passed maps: 0;
- empirical failures: mean node degree and dead-end share on all 30 maps;
- structural failures: branch-free developed corridor above 800 m on 7 maps;
- canonical audit fingerprint:
  `6ab9f8c9c62f36aeedffd67707f2c3e9072274ca91f1e836dc14d69fcde3316b`;
- generation/audit wall time: 144.26 s; maximum RSS: 272,112 KiB.

## Decision

PR62 must fail closed for default promotion. The deterministic simulation-input
substrate remains valid, but the generator needs a topology revision that
removes universal diagonal completion, introduces a real collector hierarchy,
and varies block formation by style. Threshold relaxation and renderer-only
changes are rejected.
