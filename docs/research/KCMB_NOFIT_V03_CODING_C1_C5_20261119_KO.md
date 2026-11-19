# No-fit KCMB affine envelope and V03 readiness CLI: C1–C5

Date 2026-11-19 KST. Source branch research/kcmb-v03-physical-readiness-20261119. Theory R1–R10 commit e57c4c47fdb752d3f0adf8921ce75bf9c499c5dd already independently pushed, verified against GitHub remote. Target is the original V03 21-node PLAN 1.1.26 and exact 3 city ×3 run × 24h release matrix; original native physical code and default release inputs are unchanged.

## C1 Boundary
Deliver a no-fit observation uncertainty bound using the six physical moments, plus a real-source runtime readiness scorer which never substitutes preflight or opt-in KCMB for the original packet FIFO 24h run.

## C2 Theory-to-code
Per class Y=(m0,m1,j0,j1,z0,z1), U>0. Nonnegative affine wσ(u)=Aσ(1−u)+Bσu with endpoint weights Aσ,Bσ≥0. The four supported vertex ratios are:
rσ0=U(jσ−zσ)/(mσ−jσ), rσ1=U zσ/jσ, skipping zero denominator. Their minimum and maximum give the exact SHARP attainable range over all such weights for the specified Y. No probe selection η, fitted traffic rate or sampling coefficient chosen. When pooling cells, first pool supports/numerators of the SAME common unknown affine law. Independent microscopic rational fixture yields [3.6,8.8]m/s with extrema attained by explicit vertex weights. This is conditional on the law being affine, not on the CTA mechanism being known.

## C3 Numerical safety
Moment realizability checks use pre-existing physical cone. Any empty physical support raises a typed error instead of producing a fabricated observed speed; independent particle testing and randomized physically realizable measures test every probe mean inside its envelope. Source model m, j, z and original mass ledger are read-only. Floating-point of physical moment source remains subject to original numeric tolerances; no physical data or original release thresholds altered.

## C4 V03 authority and resource
Tool tools/research/v03_readiness.py reads docs/v1/PLAN.json, scenarios/v1/release_matrix.json and optionally actual .prepare.json receipts from original tools/run_v1_local_acceptance.py. It calls the existing tools/v1_plan.py validator for DAG source evidence, then checks each whole-calendar receipt's original case, matrix SHA, 100000 resident stock, 86400s horizon, native backend, candidate source and binary SHA, wall and RSS values, immutable step. It counts 19/21 as scoped implementation progress, P01/V01/V02 dependency 3/3, complete 24h physical 0/9, and original whole-calendar preparation 0/3 without fresh receipts. The observed host has ~31.25GiB RAM rather than the user's reference 64GiB: this is an environment note, NOT a new success/failure relaxation of the process 8GiB bound.

Original release matrix includes bus capacity, stop dwell and timing assumptions and the driver has a 1000kg freight engineering prior; this scorer records these as source input conventions, NOT as physically derived no-fit theory. V03 original FIFO time-interval packet explosion at congestion remains BLOCKED, and all rates/traffic demand are unchanged.

## C5 Evidence and execution
Behavior tests first failed for missing public sharp-envelope and readiness functions (8 focused RED). After implementation tests for rational witness, randomized micro selection, equal-law pooling, degenerate state, source DAG 19/21 and fake receipt rejection are GREEN. The CLI itself had two focused expected RED cases before implementation; CLI now executes with no fresh preparations and prints exact V03 19/21, 0/3 preparation, 0/9 full-day, BLOCKED.

Files:
- src/metroflow/v1/kcmb_probe_envelope.py
- src/metroflow/v1/v03_readiness.py
- tools/research/v03_readiness.py
- tests/research/test_kcmb_no_fit_envelope_20261119.py
- tests/research/test_v03_readiness_20261119.py
- tests/research/test_v03_readiness_cli_20261119.py

No original V03 engine, PLAN, release matrix or model prior modified. Next stage C6–C10 runs actual full original 100k city calendar PREPARE-ONLY in three scenarios on this host, verifies source/provenance/resources and updates the same 21-node authority-backed numerical readiness. Each completed stage is committed and pushed with remote exact SHA readback; no PR merge/main.
