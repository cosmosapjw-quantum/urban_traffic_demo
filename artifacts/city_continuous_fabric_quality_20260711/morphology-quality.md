# City Morphology Quality Envelope

Diagnostic structural envelope only. It is not city-replication or runtime-validation evidence.

| Style | Density km/km2 | Local cells | Junction proximity | Block continuity | Four-way |
|---|---:|---:|---:|---:|---:|
| ring_radial | 17.308 | 0.618 | 0.643 | 0.973 | 0.611 |
| grid_core | 11.159 | 0.759 | 0.958 | 0.980 | 0.566 |
| polycentric_tod | 21.061 | 0.483 | 0.508 | 0.976 | 0.592 |
| river_constrained | 21.556 | 0.625 | 0.569 | 0.904 | 0.424 |
| superblock_mixed | 10.700 | 0.615 | 0.596 | 0.980 | 0.552 |
| organic | 22.451 | 0.491 | 0.451 | 0.885 | 0.439 |

## Compact CCoT

Question: Do generated styles distribute local streets beyond precinct islands?
Evidence: Three-seed 24 by 24 local-street cell presence plus the v1 structural metrics.
Inference: Style grammar changes are admitted only when local presence improves without v1 regressions.
Counterevidence checked: Static maps and named-city references are diagnostic only.
Decision: Gate v2 requires project-owned minimum local cell presence without empirical fitting.
Falsifier: Infill improves raster presence but degrades topology, OD, or visual continuity.
Next action: Visually audit the regenerated atlas before land-use coupling.
