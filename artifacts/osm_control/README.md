# OSM Control Extracts

Offline OpenStreetMap XML extracts used as a real-data reference for the
morphology instrument. They are test fixtures, not training data, and nothing in
the runtime fetches them: `metroflow.map.osm_import` reads local bytes only
(spec 039 FR-001).

Their purpose is to answer a question the project could not previously ask: if
real city data fails our own plausibility envelope, the gate or the compiler is
broken rather than the generator.

**They are not an independent positive control**, and earlier text here called
them one. Two reasons. First, `GrowthConfig.spacing_scale` was calibrated
against these same files, which makes them a development set — a generator
tuned against a fixture cannot be validated by it. Second, they are 5–12 km²
core bounding boxes, while the pinned Boeing 2019 corpus measured whole
municipalities; the two disagree by two orders of magnitude on the cities they
share (Charlotte `orientation_order` 0.002 in the corpus vs 0.1494 measured
here, Seoul 0.009 vs 0.3898). Envelope and control were never the same
population. A genuine held-out control needs new cities, peripheral and
low-density extents, and no role in any calibration.

| file | area | morphology |
|---|---|---|
| `barcelona.osm` | Eixample | modern planned grid / superblock |
| `charlotte.osm` | uptown fringe | distributed sprawl |
| `chicago.osm` | Loop / near west | gridiron core |
| `paris.osm` | Etoile | radial, Haussmann boulevards |
| `prague.osm` | Old Town | medieval organic, river-constrained |
| `seoul.osm` | Jongno | traditional complex / organic |
| `tokyo.osm` | Shinjuku | polycentric, transit-oriented |

Retrieved 2026-08-07 from the Overpass API, filtered to the OSMnx `drive`
network definition (motorway/trunk/primary/secondary/tertiary/residential/
unclassified/living_street/road plus `_link` variants; `service` excluded, as
OSMnx does) so the metrics are comparable to the pinned Boeing 2019 corpus.

Import status depends on which lane-tagging policy is selected, and earlier text
here gave the count without naming the policy:

- `lane_tagging_policy="osm_wiki"` (opt-in): **2 of 7 fail** — `paris.osm`
  (`lanes:forward` leaves no backward traffic lane) and `prague.osm`
  (`oneway=alternating`). The other five import and score.
- `lane_tagging_policy="strict"` (**the shipped default**): **6 of 7 fail**.
  Only `charlotte.osm` imports.

Every published score over these extracts is an `osm_wiki` number. Fixing the
two importer failures would widen the evidence base more than any threshold
change, since all current bands rest on n=5.

## Licence

(c) OpenStreetMap contributors, licensed under the Open Database Licence (ODbL).
See https://www.openstreetmap.org/copyright — attribution is required for any
redistribution or derived work.
