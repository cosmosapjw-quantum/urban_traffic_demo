# OSM Control Extracts

Offline OpenStreetMap XML extracts used as the **positive control** for the
morphology instrument. They are test fixtures, not training data, and nothing in
the runtime fetches them: `metroflow.map.osm_import` reads local bytes only
(spec 039 FR-001).

Their purpose is to answer a question the project could not previously ask: if
real city data fails our own plausibility envelope, the gate or the compiler is
broken rather than the generator.

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

`paris.osm` and `prague.osm` do not currently import: they use lane tagging
(`lanes:forward` exceeding total, `oneway=alternating`) that the reader does not
yet interpret. The other five import and score.

## Licence

(c) OpenStreetMap contributors, licensed under the Open Database Licence (ODbL).
See https://www.openstreetmap.org/copyright — attribution is required for any
redistribution or derived work.
