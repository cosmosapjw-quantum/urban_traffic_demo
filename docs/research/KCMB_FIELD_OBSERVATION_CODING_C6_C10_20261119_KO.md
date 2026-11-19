# KCMB Chicago observation bridge: coding C6–C10, empirical scope and reproduction

Date 2026-11-19 KST. Upstream physics parent 0855fcc633a8ad7ba8b2fa065a8db13261a48178 (physical turning pockets). New theory R1–R10 915dc8821c9dbeb3861d8fad15fa3b5e25908409, code C1–C5 0f9e7e077f79142c3892f8ba8bc72cd2cf209879. Original V1/V03 PR #41 at 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. These findings are a separate opt-in observational tool, NOT replacement/default V1 and NOT a calibrated KCMB field prediction.

## C6 Implementation and adverse diagnostics
The raw public Chicago JSON and exact query URLs were first source-frozen with independent SHA-256; the module has zero network operations and accepts no artificial count/flow label. First behavioral tests raised NotImplementedError for normalization, speed metrics and geographic match. After implementation 9/10 tests passed; geo candidate matching initially reported no OSM path despite a known connected named Halsted way. Independent Dijkstra reproduction isolated a swapped tuple unpacking: candidates are (distance,node_id) while a target loop read (node_id,distance). This was a real implementation bug and fixing it made the actual-road matching test pass. No threshold was loosened.

Strict tests: source identity/date/direction, 07:00–09:00 local ten-minute bin sequence, no overlap, raw -1 speed missingness, probe-count=0 exclusion, negative invalid speed, unverified timezone offset refusal, original source SHA mismatch and unsafe path, OSM missing name or bad endpoints, mapped segment length, CLI offline output, no invented vehicle flow/GEH. No actual field holdout data is used for calibration.

## C7 Mathematical/physical provenance

Original dataset: City of Chicago Traffic Tracker Historical 2024–2026, ID 4g9f-3jbs, CTA bus GPS estimated speeds for arterial segments. Segment 1221 northbound Halsted St Harrison→Madison, 0.52 miles (836.85888m). Local Monday 2026-04-20, 12 calibration records; Monday 2026-04-27, 12 holdout records. One sample per 10-minute bin, source speed values in mph. The source includes bus_count/message_count, which are sensor/probe diagnostics, not road vehicle counts. Valid rows 24/24, no -1 or zero probe exclusions in selected slice; mock negative tests check those guards.

Spatial quality: existing project's OSM Chicago fixture (not a remote live map) contains named Halsted highway nodes. Candidate connected undirected path: 46 OSM nodes, length 836.619050242m; endpoint spatial offsets 13.042349258m/15.702845716m; relative length difference -0.0002866. This is a plausible local centerline geometry match; OSM one-way legal route, traffic lanes, signal phase and individual CTA trace road assignment remain UNVERIFIED. The chosen City segment's NB bearing is consistent with source/end latitude increase. Provenance and a candidate node path are in CHICAGO_FIELD_RESULT.json.

Kinetic theory: equilibrium KCMB relation mu=U alpha/(alpha+nu) for alpha+nu>0. Any U≥mu, any k>0 and any tau>0 admit alpha=k mu/U, nu=k(1-mu/U), so the calibrated sample mean does not identify U, alpha, nu or tau. This experiment fits only mu_hat from calibration estimated speeds. No population-generalization CI is possible from one holdout Monday with autocorrelated ten-minute records. Speed alone does not identify density rho, so q=rho v and observed road flow/vehicle counts cannot be measured. The existing paired count-speed GEH scorer was not misused.

## C8 Actual observed scores and numerical scope

At 07:00–09:00 Chicago local:
- April 20 calibration, 12 estimated speeds; mean 17.8333333333mph=7.9722133333m/s, source range 13–21 mph.
- April 27 holdout, 12 estimated speeds; mean 18.25mph=8.15848m/s, source range 17–20 mph.
- Calibration-only speed constant mu_hat=7.9722133333m/s, actual speed-estimate holdout RMSE 0.5215466667m/s and MAE 0.3725333333m/s. This is an equilibrium-compatible **scalar baseline**, not a run of the KCMB traffic PDE/network solver.
- Clock-bin lookup template (one parameter learned from each of 12 calibration bins) holdout RMSE 1.0719642621m/s and MAE 0.9313333333m/s. It performs worse than the constant baseline on this ONE selected holdout day; no universal model comparison claim.
- Empirical W1 between calibration/holdout estimated speed distributions is 0.33528m/s, not an individual-vehicle speed or travel-time distribution test.

Actual machine-readable result: artifacts/kcmb_field_20261119/CHICAGO_FIELD_RESULT.json. Deterministic local CLI: .venv/bin/python tools/research/run_chicago_field_observations.py --output artifacts/kcmb_field_20261119/CHICAGO_FIELD_RESULT.json. It validates immutable raw source SHA before parsing, reads the original OSM fixture, executes the speed-only scorer and emits source/clock/units/geo/negative claim statuses. Runtime and CPython RSS in receipt include data parsing and geometry, not any traffic simulation. No OpenAI/web data credentials are needed at execution time.

## C9 Finite adversarial review and limitations

- **Temporal estimator**: city clock is a naive timestamp without explicit UTC offset; importer retains Chicago local-time fields and rejects caller-inserted offset. April dates avoid DST fold. Matching uses nominal 10-minute slots, not direct exact event timestamps; no hidden interpolation.
- **Vehicle population**: CTA bus GPS-derived segment estimates are not calibrated car speeds. No class-specific physical velocity likelihood or source buses vehicle-count q used. The calibration score is about the measured *proxy* only.
- **Map reference**: OSM named centerline graph distance may be close while direction legal driving restrictions, actual lane count and turn pocket shape are wrong. Output flags oneway_verified=False and lane_pocket_geometry_verified=False. This experiment cannot verify the synthetic dedicated-pocket B-throughput result.
- **Statistical uncertainty**: only one day calibration + one holdout day, 12 correlated within-day bins. No heldout-day replicate, fixed effects, sensor uncertainty covariance or i.i.d. confidence interval; the scalar baseline does not generalize until independent days/sites are tested.
- **Case selection**: one named northbound segment was chosen specifically because the repository OSM fixture covers it. This is a reproducible local proof-of-availability/measurement adapter, not representative sampling of Chicago's whole arterial network.
- **Code safety**: raw files must be beneath checked-out root and byte hashes match the frozen manifest; wrong ID/date/site or duplicate/inconsistent records fail. Invalid speed -1 is explicitly excluded and output coverage updated.
- **Performance/physics**: speed-only scores do not establish real KCMB dynamic accuracy, macroscopic network shock prediction, microscopic stop-and-go growth, or invariant entropy junction. Original V03 100k 3 cities ×3 runs×24h remains BLOCKED 0/9.

## C10 Decision / artifacts / next work

Selected scope: REAL_FIELD_SPEED_OBSERVATION_ADAPTER_VERIFIED if committed code/actual source/test logs and SHA receipt match fresh post-commit verification. Full KCMB physical field validation remains NOT_MEASURED. This negative claim boundary is productive: it makes the unsupported mapping explicit before expensive source/physics runs.

Deliver files:
- theory docs/research/KCMB_FIELD_OBSERVATION_THEORY_R1_R10_20261119_KO.md
- coding C1–C5 report docs/research/KCMB_FIELD_OBSERVATION_CODING_C1_C5_20261119_KO.md
- new importer src/metroflow/v1/chicago_observations.py
- actual immutable raw public data and SOURCE_MANIFEST.json
- tests/research/test_chicago_observations_20261119.py and test_chicago_field_cli_20261119.py
- tools/research/run_chicago_field_observations.py
- result artifacts/kcmb_field_20261119/CHICAGO_FIELD_RESULT.json
- verification logs and artifacts/kcmb_field_20261119/C10_RESEARCH_RECEIPT.json.

Next bounded physics: find actual lane/signal/demand/vehicle-count measurements and bus-specific KCMB observable operator, then run the same named road segment with exact boundary/time alignment, calibration/holdout on several independent dates, and compare speed/shock/density/flow where each is truly observed. Do not infer traffic rates from CTA probe counts or silently change original V03. Stage report is pushed only after successful regression and GitHub exact SHA readback, without any main merge or PR mutation. Native subagent execution if unavailable is NOT_RUN and separate serial evidence only.
