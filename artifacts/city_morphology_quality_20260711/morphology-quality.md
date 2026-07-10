# City Morphology Quality Envelope

Diagnostic structural envelope only. It is not city-replication or runtime-validation evidence.

| Style | Density km/km2 | Block continuity | Dead ends | Four-way | District coverage |
|---|---:|---:|---:|---:|---:|
| ring_radial | 43.208 | 0.958 | 0.075 | 0.591 | 0.981 |
| grid_core | 14.068 | 0.918 | 0.050 | 0.557 | 1.000 |
| polycentric_tod | 15.940 | 0.993 | 0.021 | 0.603 | 1.000 |
| river_constrained | 16.435 | 0.882 | 0.119 | 0.383 | 1.000 |
| superblock_mixed | 14.458 | 0.941 | 0.039 | 0.587 | 1.000 |
| organic | 17.583 | 0.991 | 0.046 | 0.373 | 0.975 |

## Compact CCoT

Question: Which generated styles fail the local structural envelope?
Evidence: Three-seed density, bridge length, degree mix, and district quadrant presence.
Inference: Style grammar changes are permitted only for stable multi-seed outliers.
Counterevidence checked: Static maps and named-city references are diagnostic only.
Decision: Keep this v1 gate scoped to local connectivity, density, and intersection mix.
Falsifier: A proposed grammar change does not improve its parent metric across all seeds.
Next action: Use visual counterevidence to design a separate global spatial-coverage probe.
