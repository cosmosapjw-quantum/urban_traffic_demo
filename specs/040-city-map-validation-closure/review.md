# PR40 Review Record

## Loop 1

- Rejected trial default promotion after material suite-time and route-ID regressions.
- Preserved source modeled length, speed, lanes, capacity, and blockability.
- Recomputed expected section catalogs rather than trusting self-fingerprints.
- Expanded replay parity to all link/node flow arrays and semantic telemetry.
- Added deterministic repeated-seed, repair-link, and bridge-link evidence.

## Loop 2

- Restored the PR35 equal-length directional physical-road invariant.

## Loop 3

- Approved with no remaining findings.

## Drift Check

- `standard` remains the deterministic runtime default.
- Planar mode is explicit and fail-closed; it is not a lane-level simulation.
- OSM remains offline reference input and is not mixed into synthetic authority.
- PNGs and wall time are diagnostic; contract/replay tests carry validation claims.
