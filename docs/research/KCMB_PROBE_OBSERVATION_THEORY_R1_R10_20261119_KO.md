# KCMB six-moment probe-selection observation: R1–R10

Date 2026-11-19 KST. Independent research branch research/kcmb-probe-observation-20261119. Parent SHA 916e5124dfa6f735cf067e596efa2b6c29411c9c. Original authoritative V1 draft PR #41 HEAD 0b9caa8cc60a3ba087722e0360b997c5dfb61d62. Preserve original main, uncommitted root files, original packet solver, campaign acceptance and all earlier branches. Status here: selected mathematical research assumptions; NOT an empirical CTA sampling-law discovery.

## R1. Original physical question and goal

The goal remains a microscopic bottom-up / macroscopic top-down traffic statistical mechanics model, with finite response and Markov switching, transport conservation, and actual observables. The previous R×C loop connected real Chicago historical CTA-bus-GPS-estimated segment speeds to the named road and a calibration/holdout split. It did NOT run the kinetic traffic model against the field. This new bounded loop derives an opt-in observation operator from the already implemented six kinetic moments, confronts its unknown probe-selection mechanism, and executes a physical scenario through the existing KCMB solver. No false traffic flow, source signal or true driver trajectory is invented.

## R2. Sources and literature

- Frozen original Chicago Traffic Tracker historical data, official dataset 4g9f-3jbs, https://data.cityofchicago.org/d/4g9f-3jbs : Halsted Street NB segment1221, 2026-04-20 calibration 12 samples and 2026-04-27 holdout 12; source SHA-256 manifests in artifacts/kcmb_field_20261119.
- Probe vehicle data sampled by time or space: Consistent travel time allocation and estimation (Transportation Research B 71 (2015), 120–137), DOI 10.1016/j.trb.2014.10.008. Time/space sampling method affects bias; no CTA-specific affine selection coefficient can be read from this paper.
- Bruwer, Walker, Andersen (2022), The impact of probe sample bias on the accuracy of commercial floating car data speeds, DOI 10.1080/03081060.2022.2150858. FCD bias depends on the probe population.
- Hellinga & Fu (2002), Reducing bias in probe-based arterial link travel time estimates, DOI 10.1016/S0968-090X(02)00003-7. Independent traffic-count observations may be necessary for actual arterial bias correction.
- Repository SSOT: src/metroflow/v1/kcmb.py, src/metroflow/v1/chicago_observations.py and existing R1–R10 kinetic moments research. Original vehicle FIFO and published model status remain unchanged.

## R3. Definitions and units

A single class has declared speed parameter U>0 m/s; microscopic realised speed v=Uu, 0≤u≤1. Internal control σ∈{0,1} switches from 0→1 at alpha≥0 s^-1, 1→0 at nu≥0 s^-1; response du/dt=(σ−u)/tau with tau>0 s. Six stored nonnegative mixed moments Y=(m0,m1,j0,j1,z0,z1), each in vehicle-equivalents:
mσ=∫1_(σ)dμ; jσ=∫u1_(σ)dμ; zσ=∫u²1_(σ)dμ.
The microscopic measure μ must be a positive measure supported on those physical states. The existing KCMB local generator, conservative flux and tests are reused byte-identically.

Declare a probe inclusion/intensity weight wσ(u)=aσ+bσu. For all physically possible u, w≥0 iff aσ≥0 and aσ+bσ≥0 for both σ. These are *hypothetical* inclusion weights, not inferred from City bus_count or message_count. If total support is zero, the mean is undefined and code returns a typed no-support result; it is NOT a zero observed speed.

## R4. Alternative mappings

A population mean U(j0+j1)/(m0+m1): correct unweighted all-class moment, but cannot automatically equal CTA-GPS bus estimates. B latent-control-only selection aσ different for 0,1: six-moment-computable, but unidentifiable from the City records. C selected affine wσ(u): exact six-moment functional, includes speed-dependent and control-dependent selection. D nonlinear weight u² or threshold censoring requires higher moments or a full velocity distribution, so no silent closure. E City actual estimator from bus GPS raw traces: unavailable; no retrospective identification of their estimator.

## R5. Constructive exact derivations

THEOREM P1: For affine nonnegative weights, weighted support D=Σσ(aσ mσ+bσ jσ) and first selected speed numerator U N=U Σσ(aσ jσ+bσ zσ), giving H_w(Y)=U N/D [m/s] if D>0. The integral formula follows directly from the generator's moment definitions, without Taylor expansion. Because 0≤u≤1 and w≥0, 0≤N≤D, so 0≤H_w≤U. A global positive rescaling of all a,b leaves H invariant. The operator is read-only and leaves vehicle conservation unchanged. Exactness applies to the declared instantaneous weight, not to the undisclosed Chicago reporting formula.

THEOREM P2: For common w=1+ηu with η≥−1 (same for both σ), set M=Σmσ, mean μu=Σjσ/M and second s2=Σzσ/M. Then
Hη = U(μu+η s2)/(1+η μu)
    = U μu + U η Var(u)/(1+η μu).
This holds for M>0 and strictly positive denominator. Thus η>0 biases the sample high, −1≤η<0 biases low; η=0 gives the population mean. Any state with Var(u)=0 has no speed-selection bias under this family. If η=−1 and all u=1, total support is zero and the observation is undefined.

THEOREM P3: At frozen switching equilibrium alpha+nu=k>0, p=alpha/k, gamma=1/tau, the exact local stationary moments per vehicle are
m0=1−p, m1=p,
j1=p(gamma+alpha)/(gamma+k), j0=p−j1,
z1=j1(2gamma+alpha)/(2gamma+k), z0=j1−z1.
Therefore E[u]=p, E[u²]=j1=p²+p(1−p)/(1+k tau) and Var(u)=p(1−p)/(1+k tau). The selected equilibrium speed becomes
Hη*=U[p+η(p²+p(1−p)/(1+k tau))]/(1+ηp).
Changing probe selection coefficient η, U and k tau can alter the predicted CTA-like speed without changing a *single observed source record*. Conversely one observed calibration mean does not determine the micro rates or sampling parameters. In particular for η=0 all positive k,tau sharing p=mu_cal/U fit the same equilibrium mean. This is parameter nonidentifiability, not strong original no-go novelty.

THEOREM P4: For disjoint cells and classes with different speeds U_a, the pooled selected-probe speed is
Hpool = [Σ_(i,a) U_a N_ia]/[Σ_(i,a) D_ia],
not the unweighted arithmetic mean of cell-level selected speeds. Proof: add independent selected numerator and denominator measures. The pooled map is exactly computable from the existing six moments (given class-wise weights) and uses no new microscopic closure.

SCOPED COUNTEREXAMPLE P5: A hypothetical weight w=u² requires E[u³] in the selected numerator, which need not be determined by (m,j,z). Let support nodes u=(0,1/3,2/3,1), baseline probabilities b=(1,3,3,1)/8, and signed vector h=(-1,3,-3,1). Then Σh=Σu h=Σu²h=0 but Σu³h=2/9≠0. For epsilon=1/32 both probability distributions μ±=b±epsilon h are positive and share the first two moments, but have different third moments. Thus w=u² selected speed is not a function of six moments without extra closure. This counterexample is specific to this projection, not a theorem against every higher-order kinetic model.

## R6. Independent physics/numerics checks and edge cases

Check mσ≥0, 0≤zσ≤jσ≤mσ, jσ²≤mσ zσ. Test positive and negative admissible η, zero-density, zero-probe support, class-dependent selection, weighted pooling, exact microscopic particle enumeration, stationary generator RHS and tau/k extreme regimes. Do not treat bus_count as a flow or weights. Temporal sampling by CTA probes may be time-based, speed- or route-biased; actual mechanism and sensor uncertainty are UNKNOWN. The model's instantaneous speed statistic is not automatically the portal's aggregation over time or route.

## R7. Executable scenario experiment

Choose a bus-labelled *hypothetical KCMB scenario* for the measured 836.85888m segment: U=30 mph=13.4112m/s, switching sum k=0.5/s, tau=3s, bus footprint 8m/vehicle-equivalent, one lane, dt=10s, assumed source inflow 0.3vehicle-equivalents/s and always-green sink. The calibration-only speed baseline mu_cal from April20 determines p=mu_cal/U under η=0. Thus alpha=k p, nu=k(1−p). Initialize at declared bounded mass and p/u mean, equilibrate with the actual Python/Rust KCMBCorridor in a finite-step warmup, then run the observation for 12 nominal 10-minute bins (separate from the real City report clock). Compare η=0,+1,−0.8 and conditional-control selection with the same physical simulation. Those η and boundary values are SCENARIO ASSUMPTIONS, not observations, so do NOT optimize them on the holdout. Report predicted probe means, actual holdout proxy RMSE, class mass ledger and ratio baseline. Assess model-vs-analytic stationary second moment independently; a source that injects fixed-speed vehicles does NOT generally preserve the exact local stationary velocity variance.

## R8. Claim admission

P1–P5 are DERIVED under stated support and selection assumptions. Actual Chicago speed rows and OSM candidate are REAL_OBSERVED_INPUT. The KCMB simulation can establish IMPLEMENTATION_VERIFIED of a *conditional scenario*, never authentic CTA estimator validation. If η=0 reproduces a fitted constant calibration mean, its holdout score is algebraically the old scalar baseline; do not present it as new out-of-sample dynamical skill. Speed-only records do not determine lane FIFO, true road vehicle flow, alpha/nu/tau, actual bus sampler or physical boundary demand.

## R9. Coding contract

Implement src/metroflow/v1/kcmb_probe_observation.py: immutable affine weights, exact per-class selected mean, pooling, stationary moment oracle, no-support handling. Add test cases from independent particle calculations and counterexample, and tools/research/run_kcmb_probe_field_scenarios.py, an offline CLI that reads the existing exact City source manifest and executes real Python/Rust KCMB timesteps under the declared hypothetical bus scenario. Serialize full source/physics/weights/timing, actual holdout RMSE, acceptance failure modes and numerical conservation. Existing src/metroflow/v1/kcmb.py and original V1 are protected: no mutation.

## R10. Stage and remote publishing

Commit/push R1–R10 theory and confirm remote exact SHA first, then TDD C1–C5 source/tests and remote push, then C6–C10 actual scenario numeric results/receipts and remote push. No merge/main change, no synthetic observations passed off as actual data, no background action after this response. Next science requires real bus probe selection/reporting specification and mapped time-resolved boundary flow/signals plus multi-date holdout to identify physical parameters and source uncertainty.
