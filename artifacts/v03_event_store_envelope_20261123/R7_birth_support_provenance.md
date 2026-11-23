# R7 — Valley 100k birth-support provenance

- Date: 2026-11-23 KST.
- Scope: supporting source tracing only; no simulation, preparation rerun, checkpoint reload, Rust/source change, commit or push was performed for this note.
- Worktree: `/home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123`.
- Traced HEAD: `eb544bc639e40e7172e1b14a0fda8dfd3c89211e`. Source hashes below identify the observed file contents; later integration must retain its own final source/binary identity.
- Authoritative original case: `valley_weekday_s7`, Valley 100k. An earlier instruction saying River was corrected before this trace.

## 1. Conclusion and claim boundary

**Derived, conditional on the declared model and exact arithmetic:** the common source calendar, causal release rule, and positive mass/moment transport provide a source-based reason to use original birth support `b in [0,t]` at a nonnegative snapshot clock `t`. Consequently an event-incidence birth measure has snapshot-age support `a=t-b in [0,t]`. This is a broad support statement, not recovery of the missing microscopic birth distribution, and does not identify a mean with an atom in the actual distribution.

**Implementation inspected:** the Python and native calendar constructors require every departure window to lie inside `[0,86400]`; the release code uses only the already due profile fraction; service vehicle offers use the current nonnegative release clock. Road events copy mass and birth moment from served parts, and compact storage copies those fields. The same calendar code covers the three original matrix cases.

**Not certified for historical floating point error:** present native summaries enclose arithmetic on the stored binary64 rows. They do not enclose all earlier solver operations, and the original checkpoint is not certified as a current-candidate time-zero run. The retained-part validator permits an absolute birth-moment slack of `1e-8`; the event checkpoint decoder checks nonnegativity but does not establish `B <= m*t`. Therefore successful decoding or a feasible aggregate mean alone is insufficient evidence of microscopic support.

**Current R6 observation status:** the first R6 receipt contains `OBSERVER_ERROR` for both observations and remains at `t=25720` with `BLOCKED_RESOURCE`. It supplies no numerical moment/support result. Its error is preserved below. The parent owns the wrapper repair and later R7 rerun; this note does not anticipate their outcome.

## 2. Original case and manifest chain

The SSOT matrix is `scenarios/v1/release_matrix.json`, SHA256:

`1eb90b60d260feff915b785ed4d425dde0bcc1601ad3ad8200640c73d765655a`.

It specifies population 100000, horizon 86400 s, repeat 3, and cases:

| Case | Declared day | Map |
|---|---|---|
| `river_weekday_s17` | weekday | `polycentric_river`, map index 4 |
| `coastal_weekend_s41` | weekend | `coastal_port`, map index 11 |
| `valley_weekday_s7` | weekday | `valley_city`, map index 12 |

The inventory departure clocks are `[21600,32400,43200,54000,64800,75600]` s. `tools/run_v1_local_acceptance.py::prepare` takes the case day into `compile_factorized_demand`, creates the inventory from this policy, and instantiates `NativeReleaseDriver` for `rust_whole`. `NativeWholeRuntime` constructs the native factorized calendar before the whole engine.

The actual earlier Valley preparation manifest is:

`artifacts/v03_age_loss_checkpoint_20261122/R10_final_native_preparation/valley_weekday_s7.prepare.json`

Its SHA256 is `f993e9fc3d65f9a489ce994010c9879da40cb8d6ca5ab3065ff9945c12c336c6`.

| Manifest field | Recorded value |
|---|---|
| case / status | `valley_weekday_s7` / `WHOLE_CALENDAR_PREPARED` |
| backend / step | `rust_whole` / 10.0 s |
| simulated / horizon | 0 / 0.0 s; preparation only |
| resident stock | 100000.0 |
| calendar legs | 918450 |
| calendar persons / vehicles | 120000.0 / 58801.0 |
| candidate git commit | `b54e45d1d73502ee52f39968d6829325859809b2` |
| candidate source SHA256 | `8fea401892df8b44a574b432e3e082f7c53c3ffc92a1867675e6f9e66c71b99f` |
| native binary SHA256 | `0eea7ad654a93ad4847e72c49df74d551f9ca38c9438370cf630dbf18d29e866` |
| source dirty | false |
| driver identity | `e77f5efaad25b7df237d91523146baacb8cbe3170bbb86594bdc0885c498fac4` |

Calendar person/vehicle totals are activity quantities from that manifest; they are not unique completed-journey counts. The manifest does not serialize every microscopic birth time. It establishes which declared calendar was actually prepared, while the constructor/source rules below provide the support argument.

The earlier `R10_current_native_25710_requested_10s.json` records an actual Valley continuation `25710 -> 25720`, status `EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON`, with full checkpoint SHA256 `447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9` and 4677350066 bytes. It explicitly records `original_candidate_from_time_zero_verified=false` and `original_full_day_acceptance=BLOCKED_0_OF_9`. These limitations are retained.

The new runner `tools/research/v03_event_store_horizon_20261123.py` declares `CASE = "valley_weekday_s7"`. The observed first R6 receipt is:

`artifacts/v03_event_store_envelope_20261123/R6_original_100k_25720_requested_10s.json`

SHA256 `acb10ec684632f96d2d2f5d0979ad6271347170761c952fe4a00d6653e45994e`.

It records start and completed clocks both 25720.0 s, status `BLOCKED_RESOURCE`, source SHA256 `620e85a5c7146de5373a11bd4e637f59de9d463d04a9f293250ce6e575dcf3e7`, binary SHA256 `734a8d320a1a1e633014c99108ec03ed5f52cb1407b26a659e1e150e8b480c4a`, source dirty false, and exact previous full-wire roundtrip true. Both native observations report:

```text
TypeError: argument 'state': 'DriverState' object cannot be converted to 'NativeWholeState'
```

No moment values or successful increased horizon are inferred from this failed observation.

## 3. Calendar support, common to all three cities

`src/metroflow/v1/schedules.py::DepartureWindow.__post_init__` requires finite start/end/weight, `0 <= start_s < end_s <= DAY_S`, positive weight, with `DAY_S=86400.0`. `DepartureProfile` requires nonempty, normalized positive windows and forbids overlap. Normalization is checked with tolerance `1e-12`; that tolerance is not a negative-time allowance.

`daily_profiles(day,purpose)` supplies the following declared windows, in hours within the day:

| Purpose | Weekday outward / return | Weekend outward / return |
|---|---|---|
| work | 7–9 / 17–19 | 9–10 / 14–15 |
| school | 8–9 / 15–16 | 10–11 / 14–15 |
| service | 10–11 / 13–14 | 10–12 / 16–18 |
| delivery | 9–10 with weight 0.6, 15–16 with weight 0.4; no return profile | same |

`demand.py::calendar_profiles` returns these profiles. `native_calendar.py::compile_native_factorized_calendar` forwards their window triples to `NativeCalendar::intern_profile`; `v1_calendar.rs::intern_profile` independently rejects nonfinite values, negative start, end beyond 86400, start >= end, nonpositive probability, and overlap.

The calendar is selected by day and purpose, not by the River/Coastal/Valley geometry. Thus the nonnegative calendar support condition applies to all three matrix cases through the common implementation. This statement does not claim that the new native build has already prepared or completed all three cases.

A direct `git show` byte comparison against the actual prior preparation commit `b54e45d1d73502ee52f39968d6829325859809b2` found identical contents for `schedules.py`, `native_calendar.py`, and `v1_calendar.rs`. This ties the inspected calendar declarations to that historical preparation, without assuming all historical engine arithmetic is identical.

## 4. Exact-model source-to-event argument

Write a source birth measure as `nu(db)`, with positive mass `m=integral nu(db)` and birth first moment `B=integral b nu(db)`. The measure is a model object; native memory retains aggregate moments rather than all its atoms or density.

1. **Causal calendar release.** In `v1_journey.rs::fraction(profile,t)`, each window contributes its overlap with `[0,t]`. The prepare loop sets `lo = released_mass / leg_mass`, `hi = min(fraction(profile,t), eligibility)` and releases only when `hi > lo`. `birth_between(profile,lo,hi)` integrates the corresponding ordered profile quantile slice and returns its conditional average birth clock. In exact arithmetic this slice lies inside `[0,t]`. Multiplying by the released mass gives its actual first moment; it is not a declaration that all travelers were born at the average.

2. **Access and dependency delay.** The same prepare loop retains `born`, combines nonnegative access-law weights with mass, and delays release through `hold` and scheduled retirement. `retire_due(t+1e-10)` eventually offers `(tag,m,m*born)`. A nonnegative delay postpones admission and does not change the retained original birth clock. The `1e-10` due-time tolerance is an implementation detail; the exact model uses causal due times, and the road-source validator separately enforces its stored moment bound.

3. **Service-vehicle convention.** `NativeServiceCore::prepare` requires a finite nonnegative clock and emits bus offers `(tag,1,t)`, freight `(tag,m,m*t)`, and direct car `(tag,m,m*t)`. These service-vehicle births equal their release tick, including when a scheduled dispatch was delayed. They are not the original passenger request birth or door-to-door journey origin.

4. **Admission and transport.** The road constructor starts at `t=0` with blank state. `v1_road.rs::step_state` admits finite nonnegative mass and moment only, checks `B <= m*t`, and rejects nonzero B for zero mass. `served_parts` multiplies m and B by the same service fraction, bounded above by one in the service calculation. Positive splitting, retention, merging and route transfer are compatible with splitting and adding positive birth measures. Such operations preserve support `[0,t]`; a later snapshot clock T >= t only widens it to `[0,T]`.

5. **Event creation.** The served-part loop appends `(tag,source,destination,m,start,end,B)` with B copied from the served part. Internal passages and final exits both create road events. Compact event packing changes representation, retaining the four floating fields; it introduces no new birth clock.

The induction is constructive at the declared-model level: start with positive profile-restricted source measures (and service vehicle atoms at their release clocks), apply the same nonnegative splits and merges, and retain the resulting measure on every emitted event. Every such event measure remains supported in `[0,T]` at a common observation time T. The missing microscopic distribution does not prevent support-based moment envelopes; it prevents selecting a unique distribution from those moments.

The induction does not say that knowledge of `0 <= B <= m*T` alone proves the actual microscopic support. For example, a distribution with negative and future births can have a mean inside `[0,T]`. Source provenance is necessary for the physical reading. Nor does the induction prove that the native proportional transport reproduces a physically exact FIFO birth distribution; this observer leaves the transport model unchanged.

## 5. Stored-f64 enclosure versus historical numerical error

Three logically distinct statements must remain separate:

| Statement | Evidence / status |
|---|---|
| Declared source model has nonnegative, causal birth support | Source construction and exact-model positive-transport argument above; **derived** |
| Current observation arithmetic encloses operations on the stored binary64 m and B values | `v1_engine.rs::event_incidence_moments` uses compensated center sums and outward-rounded intervals; **implementation inspected**, actual observation required |
| Stored values enclose the exact historical solver/model moments | No forward/interval error bound for the complete earlier run was established here; **unresolved** |

The native observer computes the common-clock first age moment `A = sum_e(m_e*T-B_e)` and separately encloses sums of m and B, with outward rounding for multiplication, subtraction and accumulation. It rejects nonfinite clock/product/accumulation. Its own docstring and output scope explicitly exclude historical integration/model error and unique-journey interpretation. It does not test the microscopic support, and it does not independently require every stored B to satisfy `0 <= B <= m*T`.

Two source checks prevent overclaiming:

- `v1_road.rs::check_state` permits `p.birth <= p.mass * state.t + 1e-8`. This is an absolute tolerance on a mass-time moment (vehicle·s in vehicle mass units). It is not a uniform time-support extension; dividing by a tiny mass can greatly enlarge the corresponding mean-time tolerance. Even the floating multiplication in the comparison is not an exact-rational support proof.
- `v1_journey.rs::NativeServiceCore::read_state` validates event mass/start/end/B as nonnegative finite values and appends them. It does not compare B with event mass times the current snapshot clock. A valid checkpoint format and a byte-exact roundtrip consequently do not establish the physical support of arbitrary decoded history.

`Fraction(float)` in the Python oracle makes subsequent calculations exact for the represented number; it does not remove prior rounding error. Intersecting the observer's arithmetic enclosure with a declared physical support is therefore a **conditional** inference. An empty intersection is a contradiction to report, not permission to silently adjust the history.

## 6. Concrete use and remaining obligation

The source evidence supports the conditional contract already used in `tools/research/v03_event_age_observation_20261123.py`: at common snapshot T, choose birth support `[0,T]`, hence age support `[0,T]`, and calculate the sharp moment envelopes. For exact mass M and age moment A, with `0 <= u <= T`, they reduce to

`K_lower(u) = max(0, A-M*u)` and `K_upper(u) = A*(T-u)/T`.

For an arithmetic rectangle `M in [M_lo,M_hi]`, `A in [A_lo,A_hi]`, the conservative conditional bounds `max(0,A_lo-M_hi*u)` and `A_hi*(T-u)/T` cover every feasible pair in the rectangle. These are useful certified calculations **conditional on the support and stored-moment interpretation**; they do not certify historical solver error. The R6 observer failure supplies no numbers for these formulas, so the later successful receipt must be the numerical source.

The minimal remaining obligations for the original saved checkpoint are explicit:

1. Obtain an actual native summary from the unwrapped native state and retain its receipt identity, clock, mass interval, birth interval, and age-moment interval. This is the parent's R7 work, not performed here.
2. If an unconditional claim about stored event rows is desired, establish feasibility against `[0,T]` with exact binary64-as-rational or directed-rounding comparisons, preferably per positive-mass row; an aggregate feasible moment can hide inconsistent rows. Such feasibility still proves only compatibility with some supported measure, while the source/model induction supplies its interpretation.
3. To upgrade from stored moments to a rigorous claim about an exact historical physical solution, supply separately bounded accumulated solver/model error or a correctly bounded replay. Neither current outward summation nor the `1e-8` state tolerance provides that bound. Until then retain `historical_solver_roundoff_certified=false` and the conditional claim status.

The observable is retained **event-incidence age at a common snapshot clock**. One vehicle may contribute at multiple internal passages; its clock is not necessarily the passenger/request clock. Do not normalize by original resident stock or label the result a unique-vehicle final-journey delay CDF. Source time windows, routes, service types and unique completion populations require explicit filtered measures and their own moments if they are to be reported separately.

## 7. Observed source identities

All paths below are relative to the stated worktree. These are read-only hashes observed during this bounded trace.

| File | SHA256 |
|---|---|
| `src/metroflow/v1/schedules.py` | `3813f82ed54231731225a59d3cf58195936b74cb20962091eb4994487d52bd95` |
| `src/metroflow/v1/native_calendar.py` | `efb3cab28d3ccc99607234ea909077ce67a00c5b38d1984e0e15fe3fec1c65cf` |
| `crates/metroflow-rust/src/v1_calendar.rs` | `b3d7402c9155205853f5380d76855e14d6f7996550356404639caaac801830c7` |
| `crates/metroflow-rust/src/v1_journey.rs` | `8366b8d9eaee24b0abfa8e214cd00cce904a1b0b5aeb4291fb41604dcdf66f20` |
| `crates/metroflow-rust/src/v1_road.rs` | `145ea322f7569320feb493e248bf9dd3c272d65681bb26266e7b4709f1ba488b` |
| `crates/metroflow-rust/src/v1_engine.rs` | `92eed5d91a7c54532f5c6d7efce5d0e6acf00fdcbaabd2192727700c4b2c751c` |

This note adds supporting provenance to the adopted moment-envelope theory and observer. It does not open a new mathematical audit or change the R7 experiment plan.

## 8. Narrow follow-up: the original Valley lower birth bound is 21600 s

**Derived for the original declared Valley source model, in exact arithmetic:** every positive-mass road event has birth support `b in [21600,T]` at snapshot `T >= 21600`. Thus use age support `[0,H]` with `H=T-21600`, provided the same source-history and numerical qualifications in sections 1 and 5 are retained. This stronger lower bound comes from source declarations and empty initial road/event queues, not from any observed mean.

The source coverage is finite and explicit:

| Source / initial state | Inspected construction and implication |
|---|---|
| Fixed fleet buses | `release_inventory.py::build_inventory` creates every corridor by iterating the original matrix `departures_s`, whose minimum is 21600. `native_static.py` serializes `c.departure_s`; `v1_engine.rs` builds each native bus with `vec![b.3]`. `NativeServiceCore::prepare` emits only when the departure/ready gate is due and uses the current tick as birth. Therefore bus birth is at least 21600. |
| Private calendar vehicles | All active work/service/outward/return profiles originate from `calendar_profiles` in the common native compiler. The earliest weekday profile is work at 25200; school, service, delivery and return windows start later. Causal profile slices and nonnegative access/dependency delays preserve this lower bound. |
| Freight service vehicles | `v1_engine.rs` constructs each service freight source at its delivery profile window end. The earlier delivery window ends at 36000, and service birth equals its actual release tick, so this class has the stronger lower bound 36000. |
| Additional direct service cars | The whole-engine constructor calls `NativeServiceCore::new(buses, people, freight, Vec::new())`; there is no separate direct-service-car source in this original pipeline. |
| Initial road state | `v1_road.rs::blank(0)` has empty packet, latent and pending collections, and zero mass totals/ledgers. The value 1 in the auxiliary Cell state vector is not an initial vehicle packet or birth measure. |
| Initial journey and event history | `NativeJourneyCore::new_shared` starts at clock 0 with three empty `StageQueue`s, zero released/completed/birth-moment vectors and empty receipt histories. `NativeServiceCore::new` starts with an empty `ChunkedEvents` history, unissued freight and unissued cars. Its bus states are waiting, not active road mass. |

The service constructor does prepopulate passenger waiting reservoirs with their declared passenger quantities. Therefore the whole service state should not be described as literally empty. Those reservoirs are not road-vehicle births at zero: passengers board only through the scheduled bus gate, and bus offers retain the release-tick birth convention. `advance_owned_joint` forms road offers from `journey.prepare()` and `service.prepare()`; the fallback `__joint_clock__` route declaration does not inject a source vehicle.

In the declared 10 s time grid, the `1e-10` due comparison cannot turn the preceding tick 21590 into a bus release before 21600. The exact-model positive-splitting/merging induction in section 4 now preserves `[21600,T]` rather than merely `[0,T]`. A time-zero run has no positive road-event incidence before 21600. No claim that the presently saved checkpoint has newly certified historical floating-point error is added.

**Concrete improvement at the known snapshot clock T=25720:** `H=4120` s replaces the earlier width 25720 s. The sharp uniform envelope-gap bound decreases from `6430*M` to `1030*M` vehicle·s, a width ratio `103/643` (about 0.1602), or approximately 6.24 times tighter. This comparison uses the source times and theorem only; no event mean or microscopic minimum was inferred. For fixed feasible exact moments and `0 <= u <= H`, the lower envelope remains `max(0,A-M*u)`, while the upper becomes `A*(H-u)/H`; for `u >= H` both are zero. A successful native observation still has to be compatible with `0 <= A <= M*H` before the narrowed support is applied to stored-moment output. With interval moments, an empty intersection must be reported rather than repaired by clipping the history.

The additional read-only source identities are `release_inventory.py` SHA256 `28c627190edeeb4d8e0f7c375c9ef55f5a7865a93b9ab267ab2ff71f3f850af8` and `native_static.py` SHA256 `e5122aed76a15da7ec90b5aae95f67b5e15778d49053c06cf3f7d6ac804f73ad`. This follow-up reads existing source/initialization only and adds this section; it performs no new experiment, data scan, implementation change, commit or push.
