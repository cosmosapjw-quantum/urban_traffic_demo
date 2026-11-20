# V03 exact source-index-view C7: current-source 100k full-city preparation and readiness

Authority: `docs/v1/PLAN.json` v1.1.26 and original `scenarios/v1/release_matrix.json`. Parent exact-view code commit `bd83579f4baa036e6bcffae0eee0a7c74fb920c1`. **Not original 24h execution or accepted release.**

## Three real whole-native source preparations

Under the original fixed 100000 residents per city, immutable three-city input matrix, 10s nominal time grid, `rust_whole`, `bounded_bytes_v1`, native_threads 1 and original 8GiB/7200s limits, we ran a fresh actual `tools/run_v1_local_acceptance.py --prepare-only` campaign after committing the exact-view native code. It generated and independently bound all three new source/native receipts to current candidate SHA256 `f5c6cedae4cec4a44dc99e2d47766a8832d67ab2dc398866b759ece02d95709c` and loaded native SHA256 `faf85c6dec661e6944f221d107b2fbe06daddf6511be50cc51415a6ee39f5f52`, `candidate.source_dirty=False`.

| Exact case | Original 100k-resident planned legs | Wall seconds | Peak RSS GiB | Status |
|---|---:|---:|---:|---|
| river_weekday_s17 | 5,093,765 | 58.895 | 2.025 | WHOLE_CALENDAR_PREPARED |
| coastal_weekend_s41 | 2,449,750 | 33.729 | 1.039 | WHOLE_CALENDAR_PREPARED |
| valley_weekday_s7 | 918,450 | 18.890 | 0.415 | WHOLE_CALENDAR_PREPARED |

All receipts have `simulated_s=0`, `horizon_s=0`: only full-demand input allocation and routing/statics preparation, **not** conservation-validated physical time evolution. Observed current host RAM ~31.25GiB, not the older reference assumption 64GiB; per-process original 8GiB remains fixed. Total planned travel legs 8,461,965, no OD reduction or parameter fitting.

## Independent source-staleness falsifier and authoritative readiness

Ran `tools/research/v03_readiness.py --prep-dir artifacts/v03_exact_interval_view_20261120/preparation --output artifacts/v03_exact_interval_view_20261120/C7_CURRENT_NATIVE_READINESS.json` with the exact rebuilt extension imported from this worktree. Scorer returned `VALID_PLAN_NOT_RELEASE`, DAG 19/21 (5 ACCEPTED, 14 VERIFIED_SCOPED), V03 directly required predecessor 3/3, current candidate 100k prep 3/3, physical 86400s runs 0/9, V03 BLOCKED and RLS01 PLANNED. Separate explicit old/current matching falsifier: three historical previous-native C9 preparation receipts are rejected **0/3** for `CURRENT_SOURCE_CONTENT_HASH_DIFFERS`; three current-native receipts are accepted 3/3 for `WHOLE_CALENDAR_PREPARATION_VERIFIED_NOT_DAY`. Thus source validity is not backfilled using earlier binaries.

Evidence: `artifacts/v03_exact_interval_view_20261120/preparation/{river_weekday_s17,coastal_weekend_s41,valley_weekday_s7}.prepare.json`, `preparation/CAMPAIGN.json` and `C7_CURRENT_NATIVE_READINESS.json`. The matching native shared object is local-only and not in Git. The original full-day 9 runs remain NOT_RUN/BLOCKED; source-bound Valley 25650→25700 for this newly compiled view remains UNRESOLVED in this C7 milestone.

## Next narrow task

A source-migration-aware **experimental** 25650→25700 replay may use the old exact 25650 binary state as a specified wire-format test input, but **must not misrepresent the previous run's source/native identity**: record old and new SHA, inspect fixed city/driver/matrix and old checkpoint SHA, check same-wire reserialization, enforce the unchanged original budgets, and label a cross-version outcome separately from a new-source 25600→25650 trajectory. If not validated, generate a fresh 25600→25650 from original input under new source before any physical comparison.
