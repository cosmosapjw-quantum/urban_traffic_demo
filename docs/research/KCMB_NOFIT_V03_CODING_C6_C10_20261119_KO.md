# KCMB no-fit model and original V03 readiness: Coding C6–C10

Date 2026-11-19 KST. Branch research/kcmb-v03-physical-readiness-20261119; parent physical research e7f03e49e5a8d3c634f469667fdc44a24cbff79e. Frozen authority: docs/v1/PLAN.json 1.1.26 and scenarios/v1/release_matrix.json. Original V03 draft PR #41 head 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. Theory R1–R10 (e57c4c47fdb752d3f0adf8921ce75bf9c499c5dd) and executable C1–C5 (f8d29188020ed692ab55c64d97b6885cd9ef89b9) already committed and pushed separately. The original V03 native road physics, release matrix, main and PR are unchanged.

## C6. Original full-calendar preparation, not just planning

Directly executed tools/run_v1_local_acceptance.py with the real source 100000 resident stock, rust_whole engine, one native worker, bounded_bytes_v1 storage and prepare-only. No demand reduction or changed fitted parameters.

City | Full original calendar legs | Actual preparation wall s | Peak worker RSS GiB | Status
River weekday seed17 | 5,093,765 | 65.169 | 2.02293 | WHOLE_CALENDAR_PREPARED
Coastal weekend seed41 | 2,449,750 | 37.585 | 1.03881 | WHOLE_CALENDAR_PREPARED
Valley weekday seed7 | 918,450 | 21.989 | 0.41598 | WHOLE_CALENDAR_PREPARED

Sum 8,461,965 exact scheduled calendar legs over three separate original city instances. Actual source and native binary sha256, release matrix, resident population, measured prep wall/RSS and native storage policy bound to each receipt. Preparation-only workers report horizon_s=0 and simulated_s=0. C1–C5 readiness originally confused this with the matrix's 86400-second full-day horizon, a real observed behavior RED. The readiness implementation and tests now accept strictly zero-horizon preparation and NEVER treat it as a 24h physical run.

The host actually reports 31.25GiB physical RAM, rather than the authoritative reference 64GiB system; original process 8GiB RSS/address-space and native accounting 6GiB were not relaxed. Prep wall/RSS do not predict congested full-day cost.

## C7. Original V03 physical prefix and exact restart

Ran the ORIGINAL rust_whole Valley physics 0→23000 simulated seconds under the original 100k calendar; nonzero traffic had not yet been triggered at 23000, so no claim about traffic dynamics was made from that zero ledger. A fresh zero→25300 original execution ran in 107.743s with peak RSS 0.45655GiB and produced actual nonzero traffic:

Vehicles requested 272.2222222222247, released 239.99999999999952, completed 0.7116492336688547, pending 32.222222222225156, active 239.28835076633067 vehicle-equivalents. Persons requested 555.5555555555671, released 300.480846487504, completed 1.1119226903036132, pending 255.07470906806316, active 299.36892379720035 person-equivalents. Cargo had zero early activation but remained present in the full frozen calendar.

Initial fresh driver reconstruction from the 23000 checkpoint encountered a driver identity mismatch with identical original candidate source/binary/matrix hashes. Root cause IMPLEMENTATION VERIFIED: step_s=10 Python integer instead of argparse-origin step_s=10.0 float changes JSON serialized native static identity, even though the physical time interval is the same. The integer static SHA was 54f88d0acb16a75f68a80e31d5d4f1e5c1ac43152a63e4ac173d35ca82bbb703; the canonical float static SHA and checkpoint identity were 2dff5dfcb8c29e7a1174847606db8f774fb31eac14d9c922c13eddc32610a235. The specialized replayer now explicitly canonicalizes the type, without changing the original physics source.

The 23000 checkpoint SHA was 12bd9498c895faab6ce744c27f2868456e89f38219fe1250fe420dd7a123b582. Fresh runtime reloaded and saved its starting state byte-identically; the resumed 23000→25300 execution took 33.509s with 0.452GiB peak RSS. Independently executed fresh 25300 and resumed 25300 native final checkpoint SHA are **identical**:
7bcbd4e7eb04d8e0014524fa815a29c56b7873c5f3bb12c37a231caa648f32e1.
The complete physical source/person/vehicle/cargo ledgers are exactly identical. This is a strict bounded original-physics reproducibility result and NOT a full-day execution or a fix for the known exponential packet split memory regime.

## C8. Parameter-independent observation bound, conditional physical state

For a fixed already constructed KCMB six-moment positive micro measure, arbitrary nonnegative affine probe selection weights have exactly attainable selected speed bounds min/max among four endpoint ratios:
U(j_sigma-z_sigma)/(m_sigma-j_sigma) and U z_sigma/j_sigma, omitting zero supports. The proof requires no chosen or fitted selection coefficients. An independent exact rational four-atom witness yields supported endpoint speeds 3.6, 6, 4, 8.8m/s, proving sharp range 3.6–8.8m/s.

Applied to the PREVIOUS hypothetical bus KCMB scenario (NOT V03 source physics), the no-fit affine envelope is [3.7012452325635,10.8419400397414]m/s and all 12 actual Chicago heldout speed proxy samples happen to fall within that broad range of width 7.140695m/s. The prior micro model assumed U=30mph, alpha+nu=0.5/s, tau=3s, source inflow=0.3 vehicle equivalents/s and bus footprint=8m: these parameters were NOT derived or observed in this study. Therefore the result is a sharp CONDITIONAL OBSERVATION UNCERTAINTY range with low empirical discrimination, not proof of independently calibrated underlying driver dynamics.

Theory R5 proves that conservation plus mean speed cannot identify alpha, nu, tau or the selection mechanism. Original release_matrix also declares synthetic engineering priors (capacity=40, dwell=20s, six departure times) and the original driver has freight 1000kg. None was silently promoted to first principles or adjusted to make a test pass.

## C9. Adversarial execution-provenance validation

C1–C5 initially accepted a set of otherwise well-shaped synthetic preparation receipts in which every city had the same arbitrary fake binary/source SHA. Added a RED counterexample with three identically forged hashes, then repaired evidence scoring to recompute source candidate_provenance and loaded native_binary_provenance directly and compare those exact SHA values to EACH city receipt. The joint 3/3 physically verified preflight flag is false when any source/native/matrix digest differs, regardless of identical text among receipts. The original physical code was not rewritten.

The replay evidence assembler requires the exact original matrix, candidate, binary and driver identities, 100000 resident count, source 23000 checkpoint digest, byte-identical fresh/resumed 25300 checkpoint digest, exact physical ledger equality, physically nonzero traffic, unchanged 8GiB process limit and explicit no full-day acceptance. Source identity is byte SHA rather than simply a prior text claim. Tests cover negative identity, time grid, forged source and malformed receipts.

Large native binary checkpoints remain LOCAL_ONLY in the isolated worktree and are intentionally not pushed as giant Git blobs. Their recorded byte lengths and hashes are published. If a future remote clone has receipts but lacks those local checkpoint bytes, the assembler MUST report local_checkpoint_bytes_verified=false and a downgraded receipt status, never claim that a locally unavailable binary was freshly checked.

Source failure types are separated: the first identity problem was implementation/serialization type, NOT physical or numerical instability; the original V03 congestion packet explosion remains BLOCKED_RESOURCE; full-day 0/9 is NOT_RUN_DEPENDENCY_BLOCKED. Wolfram computation tool was unavailable; independent exact Python Fraction witness and native checks are the real evidence.

## C10. Quantified readiness and stop condition

Authoritative 21-node DAG: 5 ACCEPTED, 14 VERIFIED_SCOPED, V03 BLOCKED, RLS01 PLANNED. Scoped complete = 19/21 (90.48%), not final acceptance. Dependencies of V03 P01,V01,V02 are 3/3 eligible. Measured original whole-calendar construction: 3/3 cities. Original nonzero-traffic bounded prefixes: 1/3 cities (Valley to 25300/86400 seconds). Exact restart comparison: 1/1 scoped attempt. Required full 24h execution: 0/9. These quantities have different denominators and must not be blended into a fabricated readiness percentage.

The original exact road time-interval FIFO scheme still exhibits partial-service duplicated row genealogy near congested times and requires a REAL original representation/semantics decision before full V03 7200s wall and 8GiB process acceptance can pass. No model simplification, mass pruning, time binning or fitted tolerance relaxation was applied. A separately accepted KCMB fixed-state model cannot silently become original V03.

Reproduction from project checkout requires building the optional _metroflow_rust native extension and using the exact release matrix. Preparation command:
python tools/run_v1_local_acceptance.py --prepare-only --matrix scenarios/v1/release_matrix.json --engine-backend rust_whole --native-threads 1 --storage-policy bounded_bytes_v1 --out artifacts/kcmb_v03_physics_20261119/preparation
Readout commands:
python tools/research/v03_readiness.py --prep-dir artifacts/kcmb_v03_physics_20261119/preparation --output artifacts/kcmb_v03_physics_20261119/READINESS_AFTER_REAL_PREP.json
python tools/research/assemble_v03_nofit_evidence.py --prep-dir artifacts/kcmb_v03_physics_20261119/preparation --output artifacts/kcmb_v03_physics_20261119/NOFIT_V03_RESULT.json

Reproduce strict source checkpoint continuation with tools/research/continue_original_v03_prefix.py using the local binary SHA-bound source checkpoint and max end time 25300. Each commit is published only after scoped Python and Rust tests, hashes and PLAN validation. Native full-city CI, PR merge/main updates and all nine full-day campaigns were NOT_RUN. NEXT scientifically productive execution: a bounded exact age-ordered temporal event representation redesign with independent equivalence tests (per-route FIFO, entry/birth/exit clocks and deterministic numerical order), before attempting the 8GiB/7200s three-city V03 campaigns.
