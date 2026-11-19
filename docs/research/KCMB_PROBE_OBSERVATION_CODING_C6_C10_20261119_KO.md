# KCMB probe-selection observation: C6–C10 numerical execution, adversarial checks, handoff

Date: 2026-11-19 KST. Research-only opt-in model. Original V1/V03 draft PR #41 head 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. Parent empirical bridge 916e5124dfa6f735cf067e596efa2b6c29411c9c. On this branch: R1–R10 theory 96e5327c0cbd9e22455f6201747b9a4db0ea6432; C1–C5 source and tests 9745c7930dea182b659a7f7b8a1b0617a3ae9605 were separately verified and pushed before this final stage.

## C6. Implementation verification, source identity, and TDD

Actual module src/metroflow/v1/kcmb_probe_observation.py implements declared AffineProbeWeights with endpoint positivity on u∈[0,1]; selected_probe_mean_speed reads the exact six kinetic moments and returns an inferred *hypothetical selected sample mean* [m/s]. pooled_probe_mean_speed uses summed physical inclusion-weighted numerator/denominator over all selected cells and times, not an unweighted average of per-cell means. stationary_six_moments evaluates a fully local frozen Markov stationary state independently of transport.

Behavior RED: initial implementation skeleton failed with 20 missing-implementation or weight validation tests; only the independently constructed nonlinear counterexample fixture was green. After implementation, the same 21 tests passed. The separate executable field-scenario CLI was also created test-first; its placeholder raised NotImplementedError in 5 behavior tests, all 5 passed after implementation.

Existing model source src/metroflow/v1/kcmb.py, original V1 physical packet runtime, City source normalized module and original 3×3×24h V03 contract are unchanged. Correctness tests include independent microscopic particle enumeration, selection weight scaling, nonnegative supports, source-state cone realizability, stationary six-moment generator RHS, two positive distributions with equal low moments and distinct nonlinear selected means, true Python/Rust physical timesteps and source/observation time identity. No synthetic field records were substituted for real City rows.

## C7. Actual physical KCMB execution with explicit conjectural boundary and observation law

The previous real data are City of Chicago Traffic Tracker historical CTA-GPS estimated speed, segment1221 Halsted Street NB Harrison→Madison, length 0.52mi=836.85888m. Raw calibration 2026-04-20 and holdout 2026-04-27 are 12+12 actual City estimates, SHA-256 verified against previously published source manifest. Both dates/time bins are held out by day (not by random within-day shuffling). Observation sampling interval is interpreted as a nominal 600s model aggregation; the City's actual estimator is UNKNOWN.

Scenario physical model (ALL EXCEPT p ARE DECLARED ASSUMPTIONS, NOT OBSERVED):
- KCMB KCMBCorridor with one spatial cell 836.85888m and 1 lane; class name hypothetical_CTA_bus_class; declared U=30mph=13.4112m/s; bus footprint=8m; source flow=0.3 vehicle-equivalents/s; sink permanently green; wave speed 5m/s.
- Markov alpha+nu=0.5/s, tau=3s, dt=10s. Only p=mu_cal/U=7.9722133333/13.4112=0.59444444444 is set from calibration mean. Set alpha=k p, nu=k(1−p). Initial 20 vehicle-equivalents, source latent probability p and injected speed fraction p.
- Model executes 240 kinetic/transport warmup timesteps then 720 forecast steps to cover 12×60 ten-second source/transport updates. Model source and sink both physically update vehicle mass/conditional moments each step; no artificial sample outputs or static equilibrium formula are inserted as a solver substitute.
- For each 600s clock bin, 60 physically simulated six-moment states are pooled by summed micro inclusion support. All three η scenarios use EXACTLY the same physical trajectory. Hypotheses: η=0; η=+1; η=−0.8. No η is fitted to holdout or claimed to describe CTA probe sampling.

The actual KCMB run gives after warmup bulk population kinetic mean speed 7.9722133333m/s (by explicit calibration construction), route-weighted dimensionless variance ≈0.08720068191585, whereas a closed frozen local stationary Markov generator at the declared k tau has variance ≈0.09643209876543. The difference is physically interpretable within the *model*: continuous injections reset new vehicle speeds to a deterministic p, and residence/transport mixing modifies the distribution. Thus substituting the closed-local stationary variance into the observation operator would be an incorrect representation of the running source/sink system. This does NOT identify actual bus speed variance from Chicago.

For the actual April27 observed 12 proxy speed rows, direct conditional scenario RMSE [m/s]:
- η=0 uniform: 0.5215466666666656
- η=+1 faster-vehicle selection: 0.7326249589269166
- η=−0.8 slower-vehicle selection: 2.029530473864696

These are holdout errors conditional on unverified observation weights and fixed assumed source flow, kinetic rates, bus U and lane geometry. The η=0 score is **algebraically the previous calibration mean baseline**, not independent physical predictive skill. The η≠0 scores show sensitivity to the unidentifiable observation selection mechanism; their worse errors on this chosen holdout day do NOT estimate true CTA weights or prove their absence.

## C8. Matched repeated performance / numerical identity

Five independent processes per backend, alternating process order Python then Rust and Rust then Python across repeats, each with 960 physical steps, same model parameters and same real observation source. Measured median KCMB physical scenario compute time:
- Python 0.0279936370207s
- Rust 0.0175017780275s
- same-physics Python/Rust ratio 1.59947

Each backend physical source mass balance has maximum absolute conservation error no larger than 1.683×10^-11 vehicle-equivalents in the checked execution. Conditional selected mean speed and heldout RMSE for all η were identical between backends to ≲10^-11m/s, within numeric tolerance. Output includes model identity, checkpoint SHA, class mass ledger, hypothetical boundary variables, holdout observable, source manifest and raw source hashes, real-data uncertainty, and processor/RSS accounting. The memory numbers are whole CPython process metrics, not comparable with the original V03 city packet solver. No claim of whole-city memory or speed improvement is made.

Raw machine-readable actual scenario output: artifacts/kcmb_probe_20261119/CHICAGO_BUS_PROBE_SCENARIOS.json. Repeats and summary: artifacts/kcmb_probe_20261119/repeats/round*_python.json and round*_rust.json, FIVE_REPEATS_PROBE_SCENARIOS.json. The mathematical map's exactness does NOT imply City CTA bus data were generated by that inclusion model.

## C9. Adversarial scientific review (bounded)

1. **Unidentified selection mechanism:** Chicago official output is an estimated road segment speed from bus GPS; unknown processing/CTA bus stops/time sampling may change selection effects. Affine w_sigma(u) is an explicit hypothetical observation model, not inferred fact. The run's selected mean is exact for that *specified* weight and instantaneous model distribution, not for arbitrary real GPS aggregation.
2. **Population and source bias:** Using a bus-labelled class is not proof that alpha,nu,tau,U match actual buses. The physically injected 0.3 vehicle-equivalents/s and footprint 8m are assumed, not obtained from City bus_count or vehicle flow sensors. The output does not convert bus_count into q or GEH.
3. **Calibration identifiability:** p=mu_cal/U under η=0 is chosen from calibration only; η=+1/−0.8 are untouched sensitivity scenarios. One 12-bin holdout Monday with within-day correlation is not an independent-day ensemble for confidence intervals. No falsely precise posterior for microscopic parameters.
4. **Observation temporal support:** The model pools one 10s snapshot opportunity per timestep into nominal 600s bins; the City reporting timestamps are 10min slots but not proof of the same sample probability/time averaging. This is a hypothesis, and within-bin real GPS event timing is missing.
5. **Conservation and realizability:** Original kinetic generator not modified. All observational function inputs are validated by moment cone constraints, positivity of weights and support; weight zero is a refusal and not zero speed. Nonlinear probe selection requires more than second moments; explicit positive-measure counterexample independently tested.
6. **Unresolved field realism:** No true signal phase, lane count, turning pocket, bus GPS raw trajectories, road flow or speed-limit measurements are available in these two City days. Hence true KCMB traffic model parameter validation and full V03 campaign remain distinct, unresolved obligations.

## C10. Scope decision and exact reproducibility

Status: SCOPED_EXACT_OBSERVATION_MAP_AND_CONDITIONAL_KCMB_RUNTIME_NUMERICALLY_VERIFIED. Real Chicago city-published source records are genuine; conditional model run is genuine; link between selection law and actual CTA reporting is unresolved. Do NOT label this “empirical predictive skill of fully calibrated KCMB”, “validated first-principles traffic model”, “real bus dynamics parameters identified”, or “full V03 production ready”.

Reproduce from project root inside independent branch research/kcmb-probe-observation-20261119:
1. .venv/bin/python -m pytest -q tests/research/test_kcmb_probe_observation_20261119.py tests/research/test_kcmb_probe_field_scenarios_20261119.py
2. .venv/bin/python tools/research/run_kcmb_probe_field_scenarios.py --backend both --output artifacts/kcmb_probe_20261119/CHICAGO_BUS_PROBE_SCENARIOS.json
3. RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --workspace --lib --offline
4. cargo check --workspace --tests --offline

Save final C10_RESEARCH_RECEIPT.json containing file SHA-256, source commit, 263 selected Python and 61 Rust test counts if and only if fresh suite confirms, numerical model output identities and negative claims. Push this final scope as its own Git commit, read back exact remote SHA. Previously pushed R1–R10 theory 96e5327c... and C1–C5 source 9745c793... remain in the same linear ancestry. No PR/main/production mutation.

Next genuinely physical research step: obtain CTA bus reporting protocol and real source flow/signal/vehicle class observation uncertainties, or an independently field-measured site with raw micro trajectories and counts. Then fit parameters only with identifiable datasets and compute calibrated multi-day holdout/flow/queue/turn metrics at equal sensor-clock/population scope, instead of increasing meta-gating.
