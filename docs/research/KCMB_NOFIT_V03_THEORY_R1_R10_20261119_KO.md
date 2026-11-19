# KCMB parameter-independent probe envelope and V03 readiness · R1–R10

Date: 2026-11-19 KST. Branch research/kcmb-v03-physical-readiness-20261119. Parent e7f03e49e5a8d3c634f469667fdc44a24cbff79e. Original V03 PR41 head 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. Authority docs/v1/PLAN.json v1.1.26 and scenarios/v1/release_matrix.json. Original main, production packet FIFO, original numerical tolerances, resource limits and release nodes are protected.

## R1. Scope
Progress the microscopic self-driven Markov / continuous-speed model and macroscopic conservative transport WITHOUT fitting new coefficients to CTA speed snapshots. Derive a parameter-free sharp envelope for speeds produced by arbitrary nonnegative *affine* probe selection applied to a fixed six-moment state. Separately execute original 100k-city V03 whole-calendar preparation and compute actual readiness directly from the authority DAG and source receipts. New KCMB physics is not the original exact-interval V03 traffic model.

## R2. Original sources
Primary project sources are src/metroflow/v1/kcmb.py, kcmb_probe_observation.py, tools/run_v1_local_acceptance.py, docs/v1/PLAN.json and release_matrix.json. V03 blockage primary measurement: artifacts/v1_v03_workspace_20261117/AUDIT_BRIEF_KO.md and RECEIPT.json.
Literature: Daganzo 1995, Cell Transmission Model Part II, DOI 10.1016/0191-2615(94)00022-R; Jin 2015, Link Transmission Model, DOI 10.1016/j.trb.2014.12.006; Bar-Gera and Carey 2022, strict FIFO CTM DOI 10.1016/j.trb.2022.04.002. Their constitutive traffic inputs or FIFO details do not prove equivalence of KCMB and this V03 engine. Exa, SciSpace, Parallel used for source discovery. Wolfram connector returned UNAVAILABLE; exact rational and reproducible Python checks replace it, rather than claiming Mathematica ran.

## R3. State and units
For physical class speed parameter U>0 [m/s] and continuous u=v/U in [0,1], control sigma∈{0,1}, define Y=(m0,m1,j0,j1,z0,z1), all in vehicle-equivalents, with j_sigma=∫u dμ_sigma and z_sigma=∫u² dμ_sigma. Nonnegative support implies 0≤z≤j≤m, j²≤m z. Any unknown affine selection intensity w_sigma(u)=a_sigma+b_sigma*u nonnegative on [0,1] is equivalent to endpoint values A_sigma=w_sigma(0)=a_sigma≥0, B_sigma=w_sigma(1)=a_sigma+b_sigma≥0. No empirical η or arbitrary A/B need be fixed.

## R4. Candidates
A. Arbitrary parameter fitting of U, alpha, nu, tau or sampling weights from 12 CTA speeds: reject as underidentified.
B. Exact V03 road packet representation replacement by KCMB fixed moments: new physical model, cannot quietly mark original V03 PASS.
C. Selected: sharp no-fit observation range for every nonnegative affine law on a given kinetic moment state + actual 100k original driver preflight.
D. Independent physical measurements of driver response, road geometry and flows: meaningful future inputs but not available in this sample.
E. Exact cumulative-count event representation: future candidate requires preserving original individual FIFO clocks, not mere state-size simulation.

## R5. Constructive derivations

THEOREM O1 (exact sharp affine range). Write w_sigma(u)=A_sigma(1−u)+B_sigma u. Define for v=(sigma,0/1):
 d_(sigma,0)=m_sigma−j_sigma; n_(sigma,0)=U(j_sigma−z_sigma);
 d_(sigma,1)=j_sigma;       n_(sigma,1)=U z_sigma.
Each d≥0, and if d=0 then n=0 for a realizable measure. For each positive d, r_v=n_v/d_v. The observed weighted numerator N and support D are sums Σ_v W_v n_v and Σ_v W_v d_v for weights W_v∈{A0,B0,A1,B1}≥0. For D>0, N/D is a convex average of the available r_v. It follows that
 H_min = min_{v:d_v>0} r_v, H_max = max_{v:d_v>0} r_v
is a SHARP interval for all nonnegative affine observation laws. Setting a single endpoint weight positive attains either extreme. If no positive supports exist, the observation is undefined; refuse rather than return zero. All endpoints are physical speeds [0,U]. The result uses ZERO fitted or arbitrarily selected sampling coefficients. □

THEOREM O2 (common selection law spatial pooling). If the same four unknown endpoint weights apply to every cell/class, pool the four supports d_v=Σ_i d_iv and numerators n_v=Σ_i U_i (dimensionless numerator_iv) BEFORE taking n_v/d_v. This yields the exact pooled sharp interval. Taking per-cell extrema then an unweighted average is not valid and would silently change the observation law. □

THEOREM O3 (micro rates not determined from conservation). The local physical equations are p'=alpha−(alpha+nu)p and m'=(Up−m)/tau. In equilibrium for k=alpha+nu>0, p=alpha/k and m*=Up. For any U≥µ, k>0 and tau>0, choosing alpha=kµ/U, nu=k(1−µ/U) gives the same equilibrium mean µ. Meanwhile stationary variance is U² p(1−p)/(1+k tau), which varies with k tau. Thus mass conservation and a calibrated mean speed do NOT uniquely select collision/switching rates or relaxation time. Parameter independence is possible for the O1 observation BOUNDS at an already known six-moment state, not for a unique unsupplied microscopic time evolution. □

THEOREM O4 (finite-route exact order information bound). Two route sequences A,B and B,A can have identical route mass and first two velocity moments while a red A / green B signal gives different exact FIFO flow. General 2m mixed route events with fixed route counts have binomial(2m,m) order possibilities, requiring at least log2 binomial(2m,m) bits for a deterministic finite-bit simulator that recovers every exact future route output. This does NOT show all lossless event representations impossible, but it shows that finite class moments alone cannot satisfy the original V03 all-route time-ordered observation contract. □

## R6. Adversarial checks
An exact rational example: four vehicle point measures with sigma0 (u=1/4,m=3),(u=3/4,m=1), sigma1 (u=1/3,m=2),(u=1,m=1), U=12 m/s. The four allowed endpoint selected speeds are exactly 18/5, 6, 4, 44/5 m/s, so the sharp no-fit interval is [3.6,8.8] m/s. Validate via independent fractions/particle enumeration and random nonnegative weights. Reject nonrealizable moments, empty support, false all-city V03 readiness, or bit-equality claims between physically different models.

## R7. Original V03 executable contract
The authoritative DAG has 21 nodes and 19 explicitly ACCEPTED or receipt-bound VERIFIED_SCOPED (90.476%). V03 BLOCKED and RLS01 PLANNED. V03 dependencies P01/V01/V02 are 3/3 eligible, NOT 3/3 full acceptance. Matrix contains 3 real cities, 100000 residents each, full 86400 simulated seconds each, three independent runs per city = 9 full days, one process 8GiB RSS and wall 7200s max, original physical coarse step 10s, plus required refined-dt checks and resume identity. Full 9-day campaign currently 0/9. The explicit stored bus/freight operational constants (bus capacity40 persons, dwell20s, six fixed departure times, freight1000kg engineering prior) are NOT derived from first principles merely because supplied by source config. Record their provenance; do not add fitted parameters or secretly alter the matrix.

C1–C5 implement a pure sharp affine envelope and original-plan readiness evaluator with tests. C6–C10 execute actual original rust_whole driver with prepare-only and all three physical 100k matrix cases, verify original source receipts, and report measured host RAM/CPU and actual per-case construction resources. This can advance the *preparation* prerequisite without changing V03 BLOCKED or 0/9 until the full physical campaign passes.

## R8. Status / gate
O1–O4 are conditional derived mathematics; exact rational and independent numerical tests will be recorded in proof. V03 19/21 is DAG implementation progress, not runtime readiness probability. Preparation-only successful output is not a full-day performance pass. Earlier measured packet explosion from exact partial head FIFO remains a genuine independent RESOURCE blocker. The actual remote host currently reports ~32GiB RAM, different from the 64GiB reference target, and CPU/memory identity must be measured in the final report.

## R9. Implementation identities
New src/metroflow/v1/kcmb_probe_envelope.py and tests/research/test_kcmb_probe_envelope_20261119.py. New tools/research/v03_readiness.py plus tests for plan/runs and source matching, independent evidence artifacts under artifacts/kcmb_v03_physics_20261119/. No change to docs/v1/PLAN.json, original native physical solver, existing matrix, V03 wall/RSS/tolerance or default engine.

## R10. Sequential publishing
Stage 1 theory and rational witness push with verified remote SHA; stage 2 executable functions and unit tests commit/push; stage 3 actual measured 100k original calendar preparation, quantified V03 subprerequisites, logs/receipts, final regression and push. No merge/main/PR update. Next physical obligation is a decision on lossless original interval representation redesign versus a *separately validated* physical approximation while keeping 100k and 24h as an actual gate.
