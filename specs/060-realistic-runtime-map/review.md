# PR60 Review Record

Status: approved
Date: 2026-07-13

## /review-spec

The explicit config pair, composed blueprint, no-repair compiler, 512-OD gate,
runtime initialization, replay fingerprint, and polygon renderer are all wired.
The default remains `standard` plus `legacy`, and cross-mode combinations fail.

## /review-code

Finding loop 1: the maximum 256 raster produced a valid-length but 74.391m2
wedge face for ring-radial seed 17. Lowering the 100m2 block threshold was
rejected. Global probes at 64, 96, 128, 192, and 256 showed that 64-192 pass;
the runtime pipeline therefore uses a bounded 128 raster for every style/seed.

Finding loop 2: eager `BlockPOI` reuse of the legacy POI enum caused a fresh
`sim.config -> city -> block_land_use -> zones -> sim.config` cycle that the
ordered suite hid. A block-domain `BlockPOIType` removed the inverted
dependency, and a fresh-process regression now locks the import boundary.

Finding loop 3: composed records initially checked CSR counts but not graph
identity, and blueprint seed was not tied to terrain seed. Blueprint and
generated-map validation now compare seed and node/link/turn authorities.
No findings remain.

## /review-drift

Question: Does the new mode form one simulation authority, or leave a static
sidecar disconnected from runtime and replay?

Evidence: all 24 required maps pass one-component, zero-repair, zero-crossing,
full geometry/section/node/turn coverage, representative reachability, and 512
sampled OD reachability. Explicit runtime init consumes the generated CSR and
block zoning, replay changes with blueprint identity, and static SVG contains
the same land-use polygons.

Inference: the realistic pipeline is now a simulation-input authority rather
than a static sidecar. Physical tick semantics remain limited until PR61.

Counterevidence checked: hidden repair, unknown mode fallback, 256-grid wedge,
single-seed success, import order, mismatched CSR, false fingerprints,
incomplete compiler coverage, unreachable OD, replay omission, and circle-only
land-use rendering.

Visual smoke counterevidence: organic seed 17 still shows a repeated diagonal
lattice, sparse/heavy backbone separation, POI overplotting, and no terrain
layer. This does not block runtime integration, but it explicitly withholds
morphological plausibility and default-promotion claims. See
`artifacts/runtime_spine_review/realistic-city-pr60-visual-audit.md`.

Decision: approve PR60 while keeping the mode explicit. Move to physical link
traversal before making traffic-realism claims.

Falsifier: hidden legacy fallback, connectivity repair, incomplete compiler
coverage, unreachable ODs, replay fingerprint omission, or circle-only zoning.

Next action: PR61 adds `spatial_queue_v1` as an explicit NumPy baseline mode
with finite storage and spillback; no default promotion.

## Gates

- targeted runtime/static: `32 passed in 148.07s`
- related integration: `99 passed in 229.41s`
- full repository: `747 passed in 503.07s`
- Ruff and diff check: passed
