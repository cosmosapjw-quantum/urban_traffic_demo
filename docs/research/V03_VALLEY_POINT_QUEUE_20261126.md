# A full-day routed-car experiment on the original Valley calendar

At 86,400 s, 57,095.9403264 vehicle-trips had finished and both observed active inventories were empty. The run stops at exactly 86,400 s. The 150 s quadrature processed 216,612,096 events on one CPU thread in 127.50 s, using 546,560 KiB peak RSS. This is evidence for a projected car transport model. Native V03 acceptance and its checkpoint, fleet and multimodal contract are separate.

## Population and route support

The input is the original 100,000-resident `valley_weekday_s7` release city and weekday factorized calendar, 918,450 legs. The directed network contains 1,586 road groups. The source Rust legal-turn solver selects one fixed route for each OD pair. Across 152,184 paired car cohorts, 304,368 calendar legs use 38,916 distinct paths. The historical native construction reports exactly those road-leg and distinct-path counts. The full city, schedule, matrix and projected input digests are in `RESULTS.json`. Extraction used the routing and calendar inputs from `5c8486cc7d8ba090b7883bff5c0f1fb3ed1448c3`. Independently repeating extraction for the access-law diagnostic reproduced the projected network byte for byte (SHA-256 `4422f446e0e9c7b3db9f361c88cfa1aa3c974e656c6ef813b2d01e22e7db5ced`).

The road experiment covers 99.1248964% of 57,600 original car-mode vehicle trips. Intrazonal car trips account for 369.2901024 veh and absent or co-located gate pairs for another 134.7695712 veh. Original calendar amounts also include 30,000 bus-person trips (1,200 occupancy-equivalent vehicles), 18,000 noncar-person trips, and 1,000 kg assigned to one freight vehicle-equivalent. These classes and the actual scheduled bus fleet remain outside the projection. The original network declares no signal plans or imposed closure windows in this case.

## Dynamics and conservation

Each purpose retains its original, piecewise-uniform departure window. A cohort has its own mass, origin, directed path and counter-direction return path. Within each time stratum the midpoint rank determines both desired departure times. A return can only depart after completion of its own outbound journey plus the original 3,600 s minimum dwell. The rank coupling of outbound and requested return, conditional-mean origin and destination access times, fixed routes, and FIFO vertical queues are explicit closures.

On link e, let τ be the original length divided by the lesser of road free speed and 10 m/s car preferred speed. Order entering packets by admission time a and stable event ordinal. For mass m and capacity c in veh/s, the packet service end is f_j=max(a_j+τ,f_{j−1})+m_j/c. The waiting time reported excludes the packet's own service time. Because a_j are ordered and travel time is constant on the link, this construction preserves FIFO and finite propagation time. Each event transfers exactly m between adjacent stages. Each completed outbound rank creates at most one return. Inducting over events gives released minus completed equal to live trip mass and road admissions minus exits equal to live road mass. At five horizons the implementation independently enumerates live masses from pending events. The largest discrepancy across all full-day and onset runs was below 1.2e−12 veh. These identities place no bound on travel-time error.

A constructive continuous boundary check follows from retaining the original origin access probability law. Before receiving constraints, its cumulative road-gate demand is A(t)=Σ_i m_i Σ_a p_i(a) F_i(t−a), with F_i the original outward departure CDF. This follows by conditioning the desired departure rank on each access atom and summing mass. The extractor evaluates the expression for three native clock boundaries without time binning, restricted to exactly the eligible car support. This makes the admission part independently testable without running the kinetic solver.

The solver preserves queue service and the finite first-passage time on each fixed route. Vertical queues permit unlimited storage and omit spillback, multi-movement junction conflict, vehicle restart and velocity dynamics. Road users share queues; the fixed-route and rank closures do not implement route or departure-choice response. The admitted-car law and outlet counts below quantify the resulting physical uncertainty.

## Numerical experiment

Full days use the following maximum departure-quantile widths. The event counts include releases, each road link and boundary transitions. Each reported wall time is one observed run, with no normalization for machine load.

| Width or intervention | Outward packets | Events | Wall s | Peak KiB | Mean trip s | Network queue veh·s |
|---|---:|---:|---:|---:|---:|---:|
| 1,200 s | 608,736 | 27,076,512 | 16.68 | 80,668 | 680.24 | 2,240,016 |
| 600 s | 1,217,472 | 54,153,024 | 31.57 | 147,048 | 652.08 | 765,158 |
| 300 s | 2,434,944 | 108,306,048 | 77.65 | 279,784 | 643.69 | 352,962 |
| 150 s | 4,869,888 | 216,612,096 | 127.50 | 546,560 | 640.10 | 180,798 |
| 300 s, 50% capacity | 2,434,944 | 108,306,048 | 92.24 | 280,136 | 644.24 | 383,451 |
| 300 s, 10% capacity | 2,434,944 | 108,306,048 | 59.75 | 280,696 | 687.57 | 2,853,525 |
| 150 s, 10% capacity | 4,869,888 | 216,612,096 | 117.01 | 547,372 | 682.39 | 2,593,317 |

The 300 s baseline identified directed group `s:g27:16>g27:17|0` by total queue delay. Both shocks modify only that group's capacity for the entire day. At 150 s, reducing it to 10% added 2,412,518.59 veh·s network waiting, raised maximum queue wait at the group from 24.93 to 5,213.73 s, and left 92.18 more vehicles on-road at 64,800 s. The independent 300 s intervention added 2,500,562.33 veh·s, 3.65% above the finer increment. Daily throughput alone conceals this cost, because every case finishes the eligible trips before midnight. The 300-to-150 s refinement nearly halves *baseline* queue delay. Departure synchronization still dominates that baseline observable. The strong intervention's increment is much more stable over the tested pair; a continuum-limit estimate is open.

The code now schedules the next outward rank lazily per cohort while preserving the original event ordinal. An independent 300 s replay of the earlier eager implementation produced identical complete text output, SHA-256 available in the JSON, in 60.56 s with 280,532 KiB peak RSS. The eager timings in the first three rows and the 50% intervention describe their original runs. The shipped runner uses lazy scheduling in all cases. A two-cohort one-road fixture separately checks the exact final trip integral 50 veh·s, queue integral 2 veh·s, and the delayed release of both return trips.

## Native snapshot and surgical revision target

The historical fresh native report is `artifacts/v03_measure_lift_20261123/S06_fresh0.json`, git `36a8b6407967a90576d94c9025ff7fa3da416301`. At 25,720 s it records 974.665851 total road admissions and 160.661779 exits. Native construction gives each scheduled bus one segment (`v1_engine.rs`, bus route construction and class ledger). Four buses have finished, zero bus mass remains on-road, and the earliest original freight window begins at 32,400 s. Subtracting four yields class-matched car admissions and exits. Each comparison uses the same city and calendar identities.

| At 25,720 s, veh | Original native car | Point queue, 20 s | Point queue, 10 s | Finest minus native |
|---|---:|---:|---:|---:|
| Road admitted | 970.665851 | 994.553490 | 996.288416 | +25.622566 (+2.64%) |
| Road exited | 156.661779 | 234.435219 | 234.622069 | +77.960290 (+49.76%) |
| On-road stock | 814.004071 | 760.118271 | 761.666347 | −52.337724 (−6.43%) |

The 60, 20 and 10 s onset integrations ran for 1.97, 5.64 and 12.10 s respectively. At 10 and 20 s the same original 07:00 onset and the observation boundary are exact bin edges. The source-law boundary convolution gives 996.646771 veh at 25,720 s, compared with 995.487828 veh under its mean-access approximation. Sampling the original source atoms one native 10 s step earlier gives 970.385779 veh, only −0.280072 veh from observed admissions. This localizes a candidate entry clock/receiving effect; proving which update causes the difference requires a native within-step observable. Refining departure bins from 20 to 10 s changed cumulative road exits by 0.187 veh while the native discrepancy remained 77.960 veh. A comparison of marked first-link entry, kinetic transit and outlet times on common routes, using the native boundary phase, is the next discriminating test. Substituting this reduced solver for a native milestone would erase that discrepancy.

## Reproduction

Use Python 3.12 with the project's dependencies, Rust/Cargo, a C++17 compiler and GNU time. The original legal-route implementation builds from the repository on Linux:

```sh
cargo build --release --locked -p metroflow-rust --manifest-path "$REPO/Cargo.toml"
mkdir -p "$REPO/native_binding"
cp "$REPO/target/release/lib_metroflow_rust.so" "$REPO/native_binding/_metroflow_rust.so"
python "$EXPERIMENT/run_point_queue.py" "$REPO" "$NEW_OUTPUT_DIR"
```

Use an empty output directory. The driver rebuilds the projection from the declared release matrix, compiles the point-queue solver, runs the analytic fixture and all ten city cases sequentially, and compares with the versioned native report. `RESULTS.json` retains source hashes, input IDs, all physical snapshots, purpose totals, native deltas, CPU-process wall times and peak RSS. Each raw solver text output is hashed and can be regenerated. Preparation took 28.58 s in the initial build. The observed 127.50 s for the finest baseline excludes preparation. This gives a measured budget for this projected observable; changing a native execution ceiling from these figures would require a native same-contract resource measurement.

The vertical-queue background is the deterministic queuing model in [Koch and Skutella, *Nash Equilibria and the Price of Anarchy for Flows Over Time*](https://page.math.tu-berlin.de/~skutella/sagt-final.pdf). Equilibrium assignment is outside this fixed-route experiment.
