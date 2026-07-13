# Feature Specification: Physical Link Traversal

Status: complete

## Goal

Add an explicit NumPy baseline traffic mode where active agents spend physical
time on links, queue at exits, and respect finite downstream storage.

## Requirements

- Add `traffic_model="spatial_queue_v1"`; preserve `point_queue_v1` default.
- Derive per-link storage in vehicles from `length_m * lanes / jam_spacing_m`.
- Advance `progress_01` by free-flow speed, tick seconds, and link length.
- Only exit-ready agents may submit turn or final-link sink demand.
- Cap realized receiving tokens by downstream free storage and prevent queue
  occupancy from exceeding storage.
- Block source admission when its first link is full; keep the trip pending.
- Preserve deterministic slot order, immutable replacement, replay, pause, and
  point-queue behavior.
- Restrict v1 to `flow_backend="baseline"`; unsupported explicit combinations
  fail closed.

## Non-goals

- No lane-level car following, shockwave calibration, Rust/GPU backend,
  traffic realism claim, default switch, or microscopic state.

## Acceptance

- Length/speed travel time, exit waiting, one-space receiving, full-link
  spillback, source admission, completion, pause, and replay tests pass.
- Existing point-queue runtime and backend tests remain unchanged.
