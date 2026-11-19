# KCMB field observation bridge: real speed data, identifiability, geography (R1–R10)

2026-11-19 Asia/Seoul. Parent 0855fcc633a8ad7ba8b2fa065a8db13261a48178, original V1/V03 draft PR41 head 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. Research only, separate worktree research/kcmb-field-observation-20261119. The production packet V1 and source campaign remain unchanged.

## R1 Physical question and claimed scope
Bridge bottom-up Markov switching + finite-response KCMB kinetic moments to top-down conservative network observables using actual historical municipal measurements. Before calculating errors, align exact observed quantity, population, road segment and clock. This research only measures an observed speed proxy and geometry matching, NOT full KCMB's causal route/flow accuracy.

## R2 Source provenance and existing results
Official City of Chicago portal dataset 4g9f-3jbs, https://data.cityofchicago.org/d/4g9f-3jbs . The portal deprecated the series on 2026-08-06, with last observations at 2026-04-30. Source documentation: https://data.cityofchicago.org/stories/s/c28d-stgw and https://catalog.data.gov/dataset/chicago-traffic-tracker-historical-congestion-estimates-by-segment-2024-current . SPEED is an estimated arterial speed from CTA bus GPS at roughly ten-minute intervals. It is NOT a direct vehicle-level speed, class-independent passenger-car measure, turning flow, or vehicle count. Speed units mph, sentinel -1 means no estimate. bus_count and message_count count source buses/probe messages, not road throughput.

Retrieved actual public segment 1221, Halsted Street northbound, Harrison to Madison, length 0.52mi, endpoints (41.874338,-87.646935) to (41.881776,-87.647171). Calibration records 2026-04-20 07:00–09:00 local, 12 rows; raw SHA256 0b3d2aa75beb7548de31417fe655ad270b3d5dcaaf392f11f6da8b8a0d93f85d. Holdout 2026-04-27 same hours, 12 rows; SHA256 0e17ba587c0ab29fbd19fe9d9d52c38ac08fa35e0ada6981ab0819c0fb061ca5. Both Mondays. Original JSON under artifacts/kcmb_field_20261119/raw/ . Each frozen source query: API /resource/4g9f-3jbs.json, explicit 14 columns, date-specific WHERE time between 07:00 and 09:00 AND segment_id=1221, LIMIT 50 ORDER BY time. These exact source slices are real, not synthesized or sampled from model output.

Prior project OSM Chicago excerpt: artifacts/osm_control/chicago.osm. Preliminary undirected named-Halsted node path gives starting endpoint distance about 11m, ending about 16m, path about 831m versus official 836.85888m (relative difference about 0.8%). Map-match is a CANDIDATE: one-way traffic law, actual turning lanes and bus road assignment not yet independently certified.

## R3 Formal quantities, units and time
For local day d and nominal ten-minute bin b, observed o(d,b) is the City-reported estimated CTA-GPS arterial segment speed [mph], converted using exactly 1mph=0.44704m/s. Length [m] uses 1mile=1609.344m. Raw source TIME has no UTC offset; retain the naive Chicago local date/time, do not invent UTC provenance. Time bin floor(clock minutes/10), 07:00–09:00. Missing/negative -1, duplicate slot, mismatched route/direction/endpoint, nonpositive bus_count, no probes, outside clock or nonfinite speed trigger exclusion with reason or explicit rejection. Never replace an observed speed with bus_count (traffic volume is unobserved).

## R4 Candidate evaluation and selection
A. Convert CTA bus probe count into vehicle throughput and use GEH: invalid observed quantity; reject.
B. Treat proxy speed snapshots as exact microscopic car follower velocities or lane turn ratios: invalid; reject.
C. Selected: speed-only holdout operator and geographic candidate match, with a KCMB equilibrium-compatible constant speed baseline, calibration/day holdout separation, and a diagnostic clock-bin template.
D. Later: combine inD micro trajectories for gaps/turns and UTD19 flow/occupancy for network density, with actual topology/clock/license. Not executed here.
E. Later: drive fully spatial KCMB with real mapped lanes, boundary class demand, signals and source times, then compare matched link speed/queue/turn flow. Current data do not identify these inputs.

## R5 Derived theory and proofs

### Theorem O1: Equilibrium speed does not identify Markov rates
Local frozen class model p'=alpha-(alpha+nu)p, m'=(U p-m)/tau with U>0, tau>0, alpha,nu>=0, alpha+nu>0. Unique stationary p*=alpha/(alpha+nu), m*=U p*. Given a single stationary mean speed mu>0 but no independent U, for EVERY U>=mu, k>0, tau>0 choose alpha=k mu/U and nu=k(1-mu/U). These give the SAME m*=mu. Even given U, equilibrium speed determines only alpha/(alpha+nu), not rate sum or tau. Thus traffic probe speed alone does not calibrate alpha,nu,tau,U. Time-resolved rates require known or independently inferred forcing and temporal population model. Direct substitution proves the continuum of equivalent parameters. This is a standard identifiability observation, not a new strong no-go.

### Theorem O2: No leakage in a speed-only day holdout score
Let calibration day c and holdout day h have disjoint local dates and the same road direction and named clock bins, with one valid sample each per bin. Calibration-only scalar equilibrium-compatible baseline mu_hat = (1/n_cal) sum o(c,b) [m/s]. Predict p(b)=mu_hat without using holdout values. Holdout MAE=(1/n_h)sum|p(b)-o(h,b)| [m/s], RMSE=sqrt((1/n_h)sum(p(b)-o(h,b))^2) [m/s]. Under equal-length arrays empirical W1=(1/n)sum_i |sort(p)_i-sort(o)_i| [m/s]; this compares estimated-speed distribution, NOT per-vehicle travel times. A clock-bin template p(b)=o(c,b) is an overfit diagnostic (one parameter per bin) and must be labelled as such. One holdout Monday with temporally correlated within-day points does not support broad frequentist population inference or a credible i.i.d. bootstrap CI.

### Theorem O3: Speed-only observations cannot determine traffic volume or travel times
Macroscopic q=rho*v requires density rho. Given v>0 and two different densities rho1,rho2, observed speed is identical but q1!=q2; therefore no observed vehicle count, queue mass or GEH from this source. CTA bus_count is an observation-probe count, not rho. Under identical positive individual traversal speeds V and fixed route distance L, Jensen yields E[L/V]>=L/E[V], but Chicago speed entries are aggregated bus GPS proxies rather than individual traversal durations; even the Jensen inequality is NOT a valid method to obtain actual trip-time ground truth from these records. The numerical value L/v is only an illustrative constant-speed proxy.

### Lemma O4: Explicit geographic road-name candidate
With WGS84 locations x=(lat,lon), distance d=2R asin(sqrt(sin^2((lat2-lat1)/2)+cos(lat1)cos(lat2)sin^2((lon2-lon1)/2))), R=6371000m. Create an undirected street graph using only OSM highway ways with an explicitly required street substring Halsted and actual node references; choose the nearest source and destination nodes, require endpoint gaps <=30m, and compute the shortest connected path. If relative length error |L_osm/L_city-1|>0.10 or disconnected, refuse a match. Positive northward trend is compatible with official NB, but a named undirected graph is NOT lane-specific traffic-law confirmation. This is an explicit quality-gated spatial CANDIDATE, not free lane geometry or a certified bus trace map match.

## R6 Adversarial risks to falsify
Reject speed sentinel -1 instead of interpreting as negative speed, missing count/probes instead of inventing count, wrong segment/direction, negative geometry, same slot duplicate, repeated date calibration/holdout, scrambled local bins, source changes above coordinate tolerance, OSM disconnected street and name mismatch. Do NOT call this a KCMB physical accuracy result. Do not fit four kinetic parameters to these 24 speed rows.

## R7 Numerical evidence scope
Raw rows verified via the official city API: 12+12 records. Calibration 17.8333mph=7.9722m/s mean, range13–21mph; holdout 18.25mph=8.1585m/s mean, range17–20mph; all 24 had positive speed estimates and probe counts. Official length 0.52mi=836.85888m. OSM named street candidate endpoints about11/16m away, undirected path about831m. These are initial direct numerical checks; machine-readable code receives an independent implementation and retains full source hashes.

## R8 Claim states
Field source accessed: ACTUAL_PUBLIC_OBSERVATION_RETRIEVED. Spatial road link: GEO_CANDIDATE, not verified turning pockets. Observed speed sample summary: NUMERICALLY_CHECKED_RAW. Equilibrium identifiability: DERIVED. Actual KCMB predictive skill: NOT_MEASURED. True car following / transition rates / flow counts: NOT_OBSERVED. Original V03 24h campaign remains BLOCKED 0/9.

## R9 Computational contract
Build opt-in src/metroflow/v1/chicago_observations.py (strict source/clock/units normalizer, same-local-bin held-out comparison and OSM name+path candidate matcher). Build tools/research/run_chicago_field_observations.py offline CLI, frozen source manifest and tests with adversarial sentinels and geometry. Output actual held-out MAE/RMSE and W1 metrics for the observable-only equilibrium-compatible baseline and overfit bin template diagnostic; do not modify the generic count/GEH scorer to fake counts, and do not change KCMB kinetic transport.

## R10 Stage publication and next action
Push this theory plus the 24 untouched official source JSON bytes under a new research branch. Then implement C1–C5 with test-driven behavior, push after scope tests. Finally C6–C10 produces raw-vs-field comparisons, hash receipt, numerical uncertainty and costs, pushes with remote SHA readback. Next genuine physical task: independently mapped real lane/signal/turn and vehicle flow data for KCMB physical calibration; not additional seals around a speed-only sample.
