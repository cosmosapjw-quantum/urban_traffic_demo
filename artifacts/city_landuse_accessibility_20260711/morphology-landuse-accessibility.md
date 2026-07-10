# Morphology Land-Use Accessibility Audit

Diagnostic only. This is not empirical validation and does not authorize PR46 or a demand-policy change.

| Style | Seed | Legacy/Morph POI valid | Legacy/Morph zone coverage | Legacy/Morph reachability | Aggregate preserved | Zones changed | POIs changed |
|---|---:|---:|---:|---:|:---:|---:|---:|
| ring_radial | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| ring_radial | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| ring_radial | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| grid_core | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| grid_core | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| grid_core | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| polycentric_tod | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| polycentric_tod | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| polycentric_tod | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| river_constrained | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| river_constrained | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 0.997 |
| river_constrained | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 0.999 |
| superblock_mixed | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| superblock_mixed | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 0.997 |
| superblock_mixed | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| organic | 17 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| organic | 29 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |
| organic | 41 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | yes | 1.000 | 1.000 |

## Compact CCoT

Question: Does morphology-aware placement preserve network accessibility?
Evidence: Multi-seed POI access validity and directed representative-zone reachability.
Inference: Structural placement is acceptable only when it retains legacy accessibility.
Counterevidence checked: Weak connectivity and visual separation alone are insufficient.
Decision: Keep this audit diagnostic; it does not authorize PR46 and no demand or route authority is changed.
Falsifier: Any run loses POI validity or directed zone-pair reachability.
Next action: Any PR46 admission requires separate decision-changing demand-defect evidence.
