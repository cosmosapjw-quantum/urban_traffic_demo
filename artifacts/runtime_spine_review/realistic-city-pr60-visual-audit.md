# PR60 Realistic City Visual Audit

Status: diagnostic smoke only
Date: 2026-07-13

## Inputs

- mode: `realistic_synthetic_v1`
- morphology: `organic`
- seed: `17`
- nodes: `1,613`
- directed links: `8,664`
- physical roads: `4,332`
- block polygons: `2,664`
- POIs: `5,744`
- HTML: generated transiently for the screenshot and not retained
- PNG: `realistic-city-pr60-organic-seed17.png`

## Adversarial Findings

1. The runtime renderer now displays actual block polygons, road ribbons, and
   POIs from the same generated authority. No precinct islands or disconnected
   components are visible.
2. The `organic` style still reads as a repeated diagonal lattice. Local block
   motifs are too regular and too similar across most of the extent.
3. The arterial/expressway skeleton is visually sparse and heavy relative to
   the local fabric, so hierarchy appears superimposed rather than grown with
   the urban tissue.
4. POI marks saturate the map and obscure block-level inspection. A review
   renderer needs deterministic sampling or density aggregation; runtime POI
   authority must remain unchanged.
5. Terrain and water are not yet visible in this integrated static artifact,
   so barrier-road-land-use consistency cannot be visually audited here.

## Decision

PR60 is acceptable as runtime integration evidence only. These findings do not
authorize morphological plausibility, traffic realism, or default promotion.
PR62 must quantify motif repetition, orientation diversity, hierarchy/local
coupling, and barrier response across the full 30-map audit. PR64 remains
blocked if those metrics or their contact sheets preserve this failure mode.
