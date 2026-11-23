# R4 rank transport implementation contract

Source ancestor: 90bfca2c2ddf081cbdf40d11b95ff820837d03b5; historical correction and merge derivation: R2_model_history_map.md.

## Intended behavior

Implement one reusable exact-rational research module, not a native V03 solver. Preserve marked mass and original birth moment, historical boundary intervals, and optional readiness targets. Fraction/int input only: accidental floating inputs are rejected. Marks identify every law/route/observable distinction required by consumers.

API:
- MarkedMass(mark, mass, birth_moment)
- RankSegment(parts, ready_target=None, boundary=None)
- RankProfile(segments).view(start=0,end=None)
- RankView.subview(start,end), moments(), iter_pieces()
- concat_adjacent(views): same immutable parent and contiguous intervals only
- RankProfile.ready_prefix(shared_displacement): unknown ready target fails closed
- ServiceWindow(start,end,rate)
- serve_windows(view,schedule,require_complete=False): prescribed service, no node solver
- transport_moments(timed_views, displacement=None, check_boundary=True): semantic-knot integration; optional explicit nondecreasing displacement validates readiness
- merge_streams(streams,target_at_end=None): exact union of input time/profile knots, conservative mark mixture, original births retained, new boundary clock recorded
- representation_stats(views): count actual distinct retained profile/segment/mark owners and views; flat profile DAG depth remains 1 (view depth2)

## Identity and metadata

Real-arithmetic semantic equivalence only. f64 operation/wire identity NOT ESTABLISHED. Unknown readiness remains None and cannot pass ready_prefix or a readiness-validated transport. Missing boundary history cannot pass check_boundary=True. Original birth time is never overwritten with node entry.

A full native state additionally needs latent class response, shared motion, node sending/receiving/storage, numerical admission boundary semantics and checkpoint mapping. This module does not infer those from first moments. Readiness targets are constant on each retained segment, matching a declared admission boundary; an end-time target callback can alter readiness when numerical admission partitions change. Partition covariance applies only when the same readiness/boundary law is preserved.

No hidden coarsening. Optional exact neighboring coalescence requires identical per-mass mark and birth slopes, readiness and affine boundary-time slope. Heterogeneous neighboring views may concatenate because their immutable parent retains every internal knot.

## Validation and bounded experiments

Primary exact checks: service against independent materialized proportional-head oracle; conservation/birth/exit moments; prefix counterexamples; unknown metadata rejection; nonproportional multi-input merge; refined time partitions; upstream FIFO; invalid service/mass/boundary checks.

Cut experiment: increasing actual output cuts under one continuous prescribed service law. Both representations consume the same schedule. Measure construction and observation separately, actual retained Python/tracemalloc/peak RSS, distinct owners, view count and essential knots. Return/query costs are part of the result.

Repeated merge experiment: phase-shifted nonproportional incoming profiles, flattening each conservative merge. Report real semantic-knot growth and runtime; do not infer global compression from cheap slices. No native full-day or V03 readiness claim.

## Origin watchdog

ALIGNED_WITH_OPEN_OBLIGATION: bulk mesoscopic mass, explicit units, causal FIFO, original birth observations and immutable state are preserved. Existing single-source prefix/inverse work is attributed; no scientific completion from owner counts. No original resident/city/dt/cap/acceptance relaxation.
