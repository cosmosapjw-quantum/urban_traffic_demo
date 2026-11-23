# MetroFlow theory-only divergent routes: coupled capacity, behavioral state, and phase measures

Date: 2026-11-23. Author pass only. No remote edits, native runs, benchmarks,
commits, or pushes were performed for this document.

## 0. Scope and evidence

The parent task supplied and verified repository identity
`492e27618696df2514b088a64de450cf69746647` at
`/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123` on device
`edd1b263-56a0-4391-8a2a-677dd00eabf5`. I read the following at that path:

- `AGENTS.md`, including the original 100k mesoscopic map–traffic–accessibility–
  lagged-development motivation and authorization for distinct controlled model
  revisions without weakening original V03 acceptance.
- `docs/v1/t02/CLOSURE_KO.md` in full.
- `crates/metroflow-rust/src/v1_kcmb_node.rs` in full.
- Relevant portions of `v1_road.rs`: class and footprint accounting,
  `motion`, `rates`, head turn fractions, receiving-space gates, and event loop.
- Scratch copy of `docs/research/V03_CAUSAL_FIFO_THEOREMS_20261123.md`.

The existing exact proportional rank cursor, sharp fixed-rank `delta/4`
certificate, and fixed-service nonexpansiveness are reused. They are not counted
as new results here. The following are direct derived results: joint arrival and
capacity bounds; a sufficient local feedback theorem; precise support-boundary
counterexamples and restorations; an exact behavioral quotient criterion;
constructive positive finite-moment reduction; and a delayed-feedback example.
The phase-measure formulation is a constructive alternative representation.
Its common-speed kinematics are equivalent to the rank kinematics under the
stated matching assumptions; continuous eligibility versus atomic packet
eligibility is a separate model/numerical choice.

Two scientifically distinct portfolio routes are retained:

**A. Retain the current hard common-speed/FIFO law and resolve its active support
boundaries.** Compress only inside strata where the actual consumers are stable.
Use cumulative service and phase measures to control feedback and observables.
Cost depends explicitly on the number of indispensable support/event boundaries.

**B. Reconstruct a finite behavioral state and, when intended, replace the
support-discontinuous speed rule by an explicitly different continuous mixture
rule.** A finite quotient can be exact only under a sufficient-state/lumpability
condition; otherwise it is a controlled model revision. This route offers a
different complexity assumption and can traverse a vanishing-class boundary.

Neither route is selected as winner, and neither is an implementation-verified
replacement for V03.

## 1. The actual closure and node operator determine the mathematical difficulty

For a cell, T02 uses class amounts `n_c [veh]`, total `N`, class weights
`w_c=n_c/N`, lane length `L_lane [m]`, and

\[
h=\frac{L_{\rm lane}-\sum_c n_c\ell_c}{N},\qquad
u_c(h)=\min\{U_{{\rm pref},c},\;{\rm cap},\;[(h-h_{0,c})/T_c]_+\},
\]
\[
U=\min_{c:n_c>0}u_c(h),\qquad
\nu_c(h)=\beta_c\frac{s_c^2}{(h+\ell_c)^2},\qquad
\dot p_c=r_c-(r_c+\nu_c)p_c,
\]
\[
\dot v=\operatorname{clip}\left(
\sum_c\frac{w_c}{\tau_c}(Up_c-v),\;-\min_{c:n_c>0}b_c,
\min_{c:n_c>0}a_c\right),\qquad \dot X=v.
\]

Here `h, ell, s` are lengths; `T_c,tau_c` are times; `r_c,beta_c,nu_c`
have units `s^-1`; `p` is dimensionless; `v,U` have units `m/s`; the clip
limits have units `m/s^2`. This is a common-speed finite-response closure,
not LWR. The native numerical method holds composition/environment during a
local step, uses latent half steps, and solves a held characteristic for motion.
This document reasons about the stated continuous closure or explicitly
identified reconstructed variants, not bit identity of that time-stepping code.

`v1_road::rates` uses head turn fractions `beta_ij`, sender priorities and
receiving rates. The event loop also gates receiving supply to zero when count
or physical lane-metres space is exhausted. KCMB uses a shared multiplier
`theta_g` for every movement of one sending group, and enforces both count and
lane-metres budgets. Thus capacity is affected by composition; it is not an
external fixed function in the complete model.

Two local discontinuities matter:

1. Adding any positive mass of a class with smaller `u_c` changes the set over
   which `U` takes a minimum. For example, `u_fast=20 m/s`, `u_slow=5 m/s`
   gives `U=5 m/s` for every positive slow-class fraction, but `U=20 m/s`
   when that fraction is exactly zero.
2. A positive head fraction for a zero-supply destination blocks a shared FIFO
   group. Removing that fraction, or averaging a rare blocked tail into the
   earlier head, can change the entire sender's service.

These are properties of the specified operator in specified topologies. They
are not a general impossibility theorem for mesoscopic traffic computation.

## 2. Jointly varying eligibility and capacity: a useful extension of the existing theorem

### Proposition A1: joint cumulative stability

Let `E,E~` be continuous nondecreasing eligible-arrival cumulative amounts on
`[0,T]`, with `E(0)=E~(0)=0`. Let `C,C~` be absolutely continuous,
nondecreasing cumulative service opportunities, both initially zero. Their
derivatives `c,c~` are nonnegative rates. Define the work-conserving departures

\[
D(t)=\inf_{0\le s\le t}\{E(s)+C(t)-C(s)\},\qquad
\widetilde D(t)=\inf_{0\le s\le t}
\{\widetilde E(s)+\widetilde C(t)-\widetilde C(s)\}.
\]

For `f=C-C~`, let `osc_[0,t] f=max f-min f`. Then

\[
\boxed{\|D-\widetilde D\|_{\infty,[0,t]}
\le \|E-\widetilde E\|_{\infty,[0,t]}+
\operatorname{osc}_{[0,t]}(C-\widetilde C)
\le \|E-\widetilde E\|_\infty+\int_0^t|c-\widetilde c|\,ds.}
\tag{A1}
\]

**Proof.** For each fixed `u<=t`, the difference of the two expressions inside
the infima is
`(E-E~)(s)+f(u)-f(s)`. Its absolute value is bounded by the eligibility
supremum plus `osc_[0,t] f`. Apply
`|inf g-inf g~|<=sup|g-g~|`, then take the supremum in `u`.
Absolute continuity gives `osc f<=Var f=integral|c-c~|`. This argument does
not divide by a service rate, so zero-capacity intervals are included.

The existing reflection argument supplies positivity, monotonicity,
`D<=E`, and service opportunity constraints. Initial eligible stock `Q0>0`
requires one extra empty-history candidate:

\[
D(t)=\min\left\{C(t),\ \inf_{0\le s\le t}
[E(s)+C(t)-C(s)]\right\},\qquad E(0)=Q_0.
\]

The same estimate holds, with the same initial convention in both systems and
any initial amount discrepancy counted in `E-E~`. One must not use the
initially-empty formula with `E(0)>0` without this correction.

### Why replacing the capacity term by `||C-C~||` is false

On `[0,2]`, in arbitrary consistent mass/time units, take

\[
E(t)=3(t-1)_+,\quad C(t)=\min(t,1),\quad
\widetilde C(t)=2(t-1)_+.
\]

The first server has service before arrivals and no service afterward; the
second has no early service and then discharges at rate two. Hence
`D(2)=0`, `D~(2)=2`, while `||C-C~||_infty=1` and
`osc(C-C~)=2`. Unused past opportunity cannot be stored. The coarse bound
`epsilon_E+2||C-C~||` is sharp in its factor two; (A1) uses the more useful
rate-integral/oscillation term.

For a marked rank cumulative `F` with Lipschitz constant `L_F`, an approximation
`F~` on the same rank domain with `||F-F~||<=eta_F` satisfies

\[
\|F(D)-\widetilde F(\widetilde D)\|_\infty
\le L_F\left[\epsilon_E+\int_0^T|c-\widetilde c|dt\right]+\eta_F.
\tag{A2}
\]

For a commodity fraction `L_F<=1`; for person, cargo, or birth-time moment
profiles the Lipschitz bound has the corresponding attribute per vehicle unit.
No normalized probability or small denominator is introduced.

## 3. A constructive coupled feedback proposition

### Proposition A2: finite-horizon continuous dependence

Choose explicit physical scales `M_* [veh]`, `T_* [s]`, `V_* [m/s]`, and
`X_*=V_* T_*`. The following norms and constants refer to the resulting
dimensionless variables; this prevents adding vehicle, speed, and latent-state
errors without conversion factors.

Consider a causal coupled model consisting of finite-response state `y`, the
reflection map above, and a service law `c=G(y,D,input)`. On an invariant
domain, suppose two trajectories obey, with past-history differences included
in `z0`,

\[
z(t):=\sup_{s\le t}\|y(s)-\widetilde y(s)\|
\le z_0+L_y\int_0^t[z(s)+d(s)]ds+\int_0^t r_y(s)ds,
\]
\[
e(t):=\|E-\widetilde E\|_{\infty,[0,t]}
\le\eta_E+L_E\int_0^t[z(s)+d(s)]ds,
\]
\[
|c(t)-\widetilde c(t)|\le L_c[z(t)+d(t)]+r_c(t),
\qquad d(t):=\|D-\widetilde D\|_{\infty,[0,t]},
\tag{A3}
\]

where the residuals are nonnegative integrable functions. They can include a
bounded behavioral reconstruction error, externally different capacity, or
admitted-demand differences. Then, with `K=L_y+L_E+L_c`,

\[
\boxed{z(t)+d(t)\le
\left[z_0+\eta_E+\int_0^t(r_y+r_c)(s)ds\right]e^{Kt}.}
\tag{A4}
\]

**Proof.** Apply (A1) to bound `d(t)` by `e(t)+integral|c-c~|`. Add the
first inequality of (A3); the result is a scalar Volterra inequality for
`z+d`. Gronwall gives (A4). If the actual causal operators satisfy these
inequalities for arbitrary candidate paths, they are a contraction on a time
interval with `Kh<1`; Picard iteration constructs a local solution. Repeating
while the invariant domain and constants remain valid gives uniqueness and
continuous dependence on `[0,T]`. The estimate alone, when known only for
already-existing solutions, is a uniqueness/stability result and must not be
misreported as an existence proof.

Fixed finite delays are included by taking `z(t)` as a supremum over the
required initial history and `[0,t]`. A delayed argument does not introduce
future information. This is finite-horizon stability; the exponential factor
can be large and does not imply asymptotic damping or useful city accuracy.

### Checkable parts of the assumptions for the present closure

On one fixed class support, require `N>=N_min>0`, `0<=h<=h_max`,
`tau_c>=tau_min>0`, `T_c>=T_min>0`, `ell_c>=ell_min>0`, and finite class
parameters. Then

\[
\left|\frac{\partial h}{\partial n_c}\right|
=\frac{h+\ell_c}{N}
\le\frac{h_{\max}+\ell_{\max}}{N_{\min}},
\qquad
\|w-\widetilde w\|_1\le\frac{2\|n-\widetilde n\|_1}{N_{\min}}.
\]

The derivative bound applies along a convex connecting domain satisfying the
same bounds; `h` is evaluated with the same lane geometry and class lengths.
The min and positive-part functions are Lipschitz, so

\[
|U-\widetilde U|\le |\mathrm{cap}-\widetilde{\mathrm{cap}}|
+T_{\min}^{-1}|h-\widetilde h|,
\qquad
|\nu_c'(h)|\le2\beta_c s_c^2/\ell_{\min}^3.
\]

For `0<=p_c<=1`, `0<=v<=v_max`, and `U<=U_max`, the unclipped acceleration
has the explicit bound

\[
|a-\widetilde a|\le
\frac{U_{\max}+v_{\max}}{\tau_{\min}}\|w-\widetilde w\|_1
+\frac{|U-\widetilde U|+U_{\max}\|p-\widetilde p\|_\infty
+|v-\widetilde v|}{\tau_{\min}}.
\]

Clipping to the same fixed-support limits is 1-Lipschitz. Latent dynamics
preserve `[0,1]`, and the acceleration is finite. A vacuum is a separate
stratum; dividing by `N` at vacuum is not covered.

For one shared FIFO sender with turn fractions `beta_j` and supplies `R_j`,
the idealized rate is

\[
c=\min\{S,\ \min_{j:\beta_j>0}R_j/\beta_j\}.
\]

On a fixed movement support with `beta_j>=beta_min>0` and bounded supplies,

\[
|\Delta c|\le |\Delta S|+
\max_j\left(\frac{|\Delta R_j|}{\beta_{\min}}
+\frac{R_{\max}|\Delta\beta_j|}{\beta_{\min}^2}\right).
\tag{A5}
\]

Zero `R_j` is permitted. A very small `beta_min` gives a very large genuine
sensitivity constant; it cannot be dismissed because the corresponding mass is
small. The native multi-sender progressive fill needs its own finite-stage
bound: fixed movement support, positive denominators for every active resource
slope, and either separated active stages or proved continuous matching at
ties. The source's numerical thresholds are an additional discrete contract.

The eligibility inequality in (A3) is also an obligation. For a fixed target
measure with cumulative `H` and density bound `H'<=rho_* [veh/m]`,
`E(t)=H(X(t))` gives

\[
e(t)\le\|H-\widetilde H\|_\infty+
\rho_*\int_0^t|v-\widetilde v|ds.
\tag{A6}
\]

This is directly checkable for a bounded continuous target density. Native
all-at-once packet readiness has target atoms and does not automatically obey
(A6). For matched moving-source cohorts, targets themselves contain `X(tau)`;
their variation must be included, rather than treating `H` as fixed.

In a network, eligible inflow also contains upstream departures. If a
componentwise bound has an extra nonnegative term `P d(t)`, it can be closed
algebraically when `rho(P)<1`, by multiplication with the positive resolvent
`(I-P)^-1`. A finite acyclic route-state graph gives nilpotent `P` and the exact
finite resolvent `I+P+...+P^(H-1)`. Positive traversal delays permit a separate
method-of-steps construction even when this instantaneous contraction fails.
None of those graph conditions has been checked for the whole native city here.

### Matching atomic events instead of assuming a density

A packet readiness event can instead be described by a guard `g(y,t)=0`.
If a neighborhood has a unique matched crossing with
`|d g/dt|>=m>0`, uniform guard perturbation at most `epsilon_g` shifts the
event time by at most `epsilon_g/m`. For **continuous physical states with
mode changes but no state jumps**, finitely many separated matched events,
bounded pre/post-event vector fields and phasewise Lipschitz dynamics permit
concatenated same-clock state estimates. The interval in different modes adds
at most a vector-field difference bound times the event-time shift, followed
by the phasewise amplification. A continuous departure integral with bounded
service has the analogous rate-bound times time-shift contribution.

This statement does not cover jumps merely because their reset is Lipschitz.
For example y'=0, reset R(y)=y+1 at time1 versus time1+epsilon has transversal
guards and a Lipschitz reset, but same-time sup|y-ytilde|=1 for every epsilon>0.
Such matched jump histories need an explicit event-aligning time change
(and a compatible Skorokhod/event-aligned metric), or a separate atom error
term. An atomic completion-CDF jump has the same limitation. No new jump-metric
theorem is asserted here. Native atomic eligibility is therefore an explicit
event-handling obligation, not an automatic instance of density bound (A6).

This correction was identified during the single fresh independent R6 review
and integrated before publishing the proof packet.

Tangential arrival at a stopping point, simultaneous reordered events, changed
movement support, or an unbounded number of switches require a new local
analysis. The proposed route keeps those boundaries explicitly and charges
their count to complexity; it does not cross them by applying a smooth theorem.

## 4. Route A: support-aware conservative phase and rank measures

### 4.1 Physical state and initial/boundary data

Let `q [veh]` be FIFO rank; `zeta` contains class, purpose, information state,
route state and fixed per-vehicle attributes. Let `b [s]` be original birth
time, distinct from local link entry time. A link of length `L>0` stores a
nonnegative marked measure `mu_t(dq,dx,db,dzeta)` and common finite-response
state `(v,p_c)`. Interior characteristics satisfy `dx/dt=v(t)`, while age
`a=t-b` satisfies `da/dt=1`.

For an admitted cohort entering at time `tau`,

\[
x(t;\tau)=\min\{L,X(t)-X(\tau)\},\qquad
X(t)=\int_0^t v(s)ds.
\]

The endpoint atom at `x=L` is eligible stock waiting for node service. An
increasing departure rank removes only a prefix, `0<=D(t)<=E(t)`. Interior
advection is equivalently

\[
\partial_t f+\partial_x(vf)+\partial_a f=0
\]

with boundary admission at `x=0`, and a retained ordered queue at `x=L`.
An endpoint atom described only by total mass loses FIFO tie order; rank or
entry-order information must remain attached. Initial stock requires its
distance/target profile and initial ordering, as well as `(v(0),p(0))`.
Total initial stock and one birth moment cannot determine first-passage times.

With common nonnegative speed, earlier entrants have no smaller displacement.
If the initial profile is nonincreasing in rank, characteristics preserve that
order, and prefix discharge preserves FIFO. A continuous phase measure is a
choice of resolved eligibility; it is not automatically equal to a source
packet whose entire mass becomes ready at one native event.

The clipping map `x -> min(L,max(0,x))` is 1-Lipschitz. For equal-mass, matched
initial cohorts under two common speed histories, the unnormalized spatial Wasserstein-1
transport contribution (with units vehicle-metres) is bounded by initial spatial transport error plus
`M integral|v-v~|dt`. Matched later arrivals satisfy the same individual bound
from their admission time. Differing admission/departure masses require an
unbalanced or bounded-test-function metric and a separate mass error term.
This transport calculation does not by itself control the node boundary.

### 4.2 Additive conservation and residence observations

For any attached additive attribute `phi(zeta,b)`, conservative transport gives

\[
M_\phi(t)=M_\phi(0)+A_\phi(t)-D_\phi(t).
\tag{A7}
\]

Use `phi=1` for vehicles, `phi=o(zeta) [person/veh]` for persons,
`phi=g(zeta) [kg/veh]` for cargo, and `phi=b [s]` for vehicle-birth-time
first moment. The same transfer appears with opposite signs at adjacent links,
so internal transfer cancels in network ledgers. Boarding, unloading, mode
changes, and journey completion need explicit exchange/source/sink ledgers;
the road argument does not make them disappear.

If `B=integral b dmu`, total origin residence stock is

\[
R(t)=tN(t)-B(t)\quad[\mathrm{veh\,s}],\qquad
\dot R=N+\int(t-b)d\dot A-\int(t-b)d\dot D.
\tag{A8}
\]

For freshly born source entries with `b=t`, the source age term vanishes.
Internal entries retain the original birth time. Thus retaining `N` and `B`
gives exact residence stock for a given retained measure; retaining only a
mean departure age without its mass is not sufficient.

For a common observation time,
`|Delta R|<=t |Delta N|+|Delta B|`. Average travel time or age requires a
strictly positive observed completion amount. Division by a vanishing amount
has no uniform error bound. Likewise, a count error `epsilon` gives an inverse
departure-time error at most `epsilon/s_min` only on a rank neighborhood where
the reference cumulative departure grows at least at rate `s_min>0`.
An identically zero service interval is allowed by (A1), but invalidates this
inverse-time conversion for ranks spanning the flat region.

### 4.3 Why support-aware partitioning is necessary

Take a FIFO queue of total amount one, with a pure unblocked prefix A of amount
`1-epsilon` and a pure blocked suffix B of amount `epsilon`. Sender capacity
is one; A's receiver has ample supply; B's receiver has zero supply. The
original queue discharges `1-epsilon` by time one and stops at B.

Replace the queue by one homogeneous block with the same exact A and B totals.
Its head has B fraction `epsilon>0` immediately, so the common FIFO multiplier
is zero from the beginning. The original and reconstructed B prefix cumulatives
differ by at most `epsilon(1-epsilon)` but the departures differ by
`1-epsilon` at time one. Every whole-queue mass, person, and cargo total can be
identical in this example.

For `epsilon=10^-4`, the exact errors are
`eta_B=9999/100000000 veh` and `Delta D=9999/10000 veh`.
This refutes uniform continuity of this node solution map in that cumulative
composition metric across the zero-supply/support boundary. It does not refute
controlled approximation on a restricted domain or with additional support data.

Three concrete restorations are different model choices:

1. Retain the A/B support change as a mandatory rank boundary; the example is
   then represented exactly with two blocks for every `epsilon`.
2. Restrict supplies to `R_j>=R_min>0`. A rare movement with
   `beta_j<=R_min/S_max` cannot bind a sender of rate at most `S_max`.
   This is a domain restriction, not a way to handle real red lights.
3. Use physically separate turning pockets if geometry and lane access permit
   them. This changes the FIFO grouping and needs its own space and access
   accounting; it cannot be introduced merely by renaming a blocked mixture.

Preserving only the union of labels somewhere in the whole queue is
insufficient. The relevant support is the exposed head/decision stratum. A
support-aware rank grid retains all mandatory boundaries and adds maximum mass
resolution `delta` inside them. With queued amount `M` and `J_sigma` mandatory
internal boundaries, a constructed partition has at most
`ceil(M/delta)+J_sigma` blocks. The inherited cumulative marked error is
controlled inside these intervals, while active support boundaries remain exact.

This is a real cost/accuracy statement. There is no bound on `J_sigma` from
`M` alone; a highly alternating queue may require many boundaries. A practical
fixed-memory claim would additionally require a regularity/finite-switch
assumption or adoption of route B.

## 5. Companion route and one explicitly changed closure

The separate behavioral-quotient author supplies the exact quotient and
bounded sufficient-state route. The interface with this note is precise:
retain class, purpose, information, route-state and additive ledger features;
prove that every label in one quotient state has the same transitions into
each other state for each allowed environment. Equal current next movement
alone is insufficient when later route suffixes or information differ.
Any residual consumer error must be passed to `r_y,r_c` in (A3), and an
unretained support indicator at a zero-supply destination is not a small
residual. This note does not duplicate that author's full quotient derivation.

A small independent illustration relevant to that interface is retained:
under the actual affine latent law `p'=r-lambda p`, polynomial moments satisfy

\[
\dot m_k=k r m_{k-1}-k\lambda m_k.
\]

Thus a fixed polynomial moment space is invariant within a common class and
environment. Equal weights on `p={0,1/4,1/2,3/4,1}` and weights
`(1/4,1/2,1/4)` on `p={0,1/2,1}` both have moments
`(m0,m1,m2)=(1,1/2,3/8)`. With `r=1/5 s^-1`, `lambda=1/2 s^-1`,
both derivatives are `(0,-1/20,-7/40)`. Positive moment matching has a standard
finite-feature foundation in Bayer–Teichmann, but dynamic equivalence still
requires an invariant feature space and sufficient-state consumers. A reference
to that theorem cannot replace the behavioral condition.

### Ancillary alternative: support-continuous target speed

The hard minimum in Section 1 is discontinuous when a slow class vanishes.
An optional replacement, with `kappa>0 [m/s]`, is

\[
U_\kappa(w,h)=-\kappa\log\left(\sum_c w_c
\exp[-u_c(h)/\kappa]\right).
\tag{B1}
\]

It equals `u_c` for a pure class, is nonnegative for nonnegative targets, and
satisfies

\[
\min_{c:w_c>0}u_c\le U_\kappa\le\sum_c w_cu_c,
\quad
0\le U_\kappa-U\le\kappa\log(1/w_{c_*})
\tag{B2}
\]

for a minimizing class `c_*`. The last inequality follows by retaining its
single term inside the logarithm; the weighted-mean bound follows from convexity
of the exponential. On `0<=u_c<=u_max`, the denominator is at least
`exp(-u_max/kappa)`, giving the safe weight-Lipschitz bound
`|Delta U_kappa|<=kappa exp(u_max/kappa)||Delta w||_1`, including zero
weights. The hard minimum is recovered as `kappa -> 0` on each fixed positive
support, not uniformly as the minimizing weight tends to zero.

For `u_fast=20`, `u_slow=5 m/s`, `w_slow=10^-4`, and `kappa=5 m/s`,
the hard target is `5 m/s`, while
`U_kappa=20-5 log[1+10^-4(exp(3)-1)] = 19.9904663264 m/s`.
This explicitly exceeds the original slow class's admissible target. If that
target is an inviolable safety/admissibility constraint, this replacement is
not a valid approximation to the original model. It is only a separate
behavioral model in which those class values represent preferences negotiated
into a shared target. No equivalence or inherited noncollision claim applies.

Finite response can be retained by replacing only `U` and using fixed
class-catalogue clip limits `a_*=min_c a_c`, `b_*=min_c b_c`; these acceleration
limits remain no larger than each admitted class limit and do not jump at
vanishing mass. Legal/geometric hard limits must remain hard limits.
Common-speed FIFO kinematics then remain as in Section 4, but the junction
zero-supply discontinuity remains unresolved by (B1). This option stays an
ancillary divergent alternative; it is not the proposed default replacement.

## 6. Traffic, accessibility, and lagged development: a nontrivial feedback calculation

The following is an illustrative local linearization, not a readout of the
native M04 implementation. It supplies exact obligations for a later mapping
to that implementation.

On a busy, unclipped branch, let occupancy `n [veh]`, speed `v [m/s]`, and
service `c=gamma v [veh/s]` obey

\[
\dot n=a-\gamma v,\qquad
\tau_v\dot v=U_0-\kappa_n n-v.
\]

Here `gamma [veh/m]` converts speed to flow, and
`kappa_n [m/(s veh)]` is the density-induced target-speed slope. The perturbation
matrix has characteristic polynomial

\[
\lambda^2+\lambda/\tau_v-\gamma\kappa_n/\tau_v.
\]

For positive coupling its larger root is
`[-1+sqrt(1+4 gamma kappa_n tau_v)]/(2 tau_v)>0`.
This is a concrete positive traffic feedback: more stock reduces speed,
reducing service and increasing stock further. Existence and finite-time
continuous dependence remain valid, but asymptotic stability fails on that
linear branch.

Introduce demand damping `a=a0-k n`, `k [s^-1]`. The characteristic polynomial
becomes

\[
\lambda^2+(k+1/\tau_v)\lambda+
(k-\gamma\kappa_n)/\tau_v.
\]

It is Hurwitz exactly when `k>gamma kappa_n` (with positive `k,tau_v`).
This is the smallest damping threshold for this specified two-state model.

Now let `z` be a development-driven demand state, let increasing occupancy
reduce accessibility, and include a causal delay `d>=0`:

\[
\delta\dot n=-k\delta n-\gamma\delta v+\beta\delta z,
\quad
\tau_v\delta\dot v=-\kappa_n\delta n-\delta v,
\quad
\tau_z\delta\dot z=-\chi\delta n(t-d)-\delta z.
\tag{C1}
\]

Choose development units so `beta [veh/(s zunit)]` and
`chi [zunit/veh]`; then `beta chi` has the same `s^-1` unit as `k`.
The sign of the actual native development response must be established, rather
than inferred from this example.

### Proposition C1: a sufficient delay-robust condition

For positive response times and finite delay, the explicit sufficient condition

\[
\boxed{k>\gamma\kappa_n+\beta\chi}
\tag{C2}
\]

gives exponential decay of (C1), uniformly over allowed histories with a finite
weighted supremum. To construct a decay certificate, choose positive weights
`w_n,w_v,w_z` and `eta>0` satisfying

\[
(k-\eta)w_n>\gamma w_v+\beta w_z,
\quad (1-\eta\tau_v)w_v>\kappa_n w_n,
\quad (1-\eta\tau_z)w_z>\chi e^{\eta d}w_n.
\tag{C3}
\]

Such weights and a sufficiently small positive `eta` exist under (C2): start
with `w_n=1`, `w_v` just above `kappa_n`, and `w_z` just above `chi`, then
use continuity in `eta`. After rescaling states to these weights, assume a
first crossing of the envelope `M exp(-eta t)`. The upper right derivative
of the absolute value of each component is bounded by its diagonal damping
plus the absolute cross couplings; a delayed component contributes
`exp(eta d)`. Each inequality in (C3) makes the first crossing impossible.
This proves the envelope and exponential decay.

This sufficient condition is conservative because it discards the negative
feedback sign of the development response; it is not a necessary threshold.
In a checked dimensionless example `gamma=.4`, `kappa_n=.5`, `tau_v=2`,
`k=.6`, `beta=.1`, `chi=.5`, `tau_z=10`, `d=3`, choose
`(w_n,w_v,w_z)=(1,.6,.6)` and `eta=.005`. The three strict slacks in (C3)
are `.295`, `.094`, and `.0624434677`; the small-gain margin in (C2) is
`.35`. Without the damping term, the positive eigenvalue is
`.1531128874` per chosen time unit.

To use this with the actual city, one must identify causal accessibility
observables and the derivatives/gains of demand, routing and development,
including the actual lag kernel. If accessibility is a discontinuous cutoff
of an unbounded travel-time inverse, (A4) is insufficient. A bounded Lipschitz
kernel of measured time/cost has a direct composition bound once the cost
error is controlled; threshold accessibility instead needs a margin or a bound
on opportunity mass near the threshold. Land-development sensitivity remains
a separate downstream obligation.

## 7. Complexity versus resolution and observation

| Object | Constructive state size | Controlled quantity | Condition not supplied for free |
|---|---:|---|---|
| Support-aware rank/phase blocks | `O(K [ceil(M/delta)+J_sigma])` for `K` retained marks/features | Cumulative marked amounts; phase transport; exact support events | `J_sigma` may grow with real behavioral alternation |
| Positive moment reconstruction per retained block | At most `m` atoms for `m` features | Exact chosen moments; separate consumer residual | Future closure requires invariant features, or bounded residuals |
| Finite behavioral quotient | Number of retained behavioral states times spatial/rank blocks | Exact state totals under the companion quotient condition | Individual suffixes/information must be sufficient-state equivalent |
| Spatial phase mesh of width `Delta x` | Typically `O(L/Delta x)` per retained behavior state | Wasserstein/bounded-test spatial error | Queue tie order, boundary service, and eligibility error are additional |
| Full feedback | State/feature errors multiplied by explicit finite-time gain | Bound (A4), or contractive example (C3) | Constants and active-domain margins must be measured or proved |

Here `K,m` are model-dependent feature counts, not automatically constants
independent of route diversity. A finite-mass rank grid controls mass resolution;
a spatial grid controls distance resolution; time integration controls temporal
truncation. These are distinct approximation parameters and require separate
budgets. Merely imposing a maximum block size gives no state-count bound unless
the actual partition construction and mandatory boundary count are also given.

## 8. Actual small checks and literature relationship

Executed locally in scratch:

`python /workspace/scratch/cd2a858c7a5c/check_controlled_routes.py`

Results are in `metroflow_controlled_routes_checks.json`. The program imports
the existing exact-rational piecewise-linear reflection helper; it is a small
mathematical check, not production code or native validation.

- 128 exact-rational pairs with both eligibility and capacity changed satisfied
  (A1). Full continuous suprema included internal queue-emptying knots.
  Independently computed queue-balance recurrences agreed exactly.
- The changing-capacity sharp example gave capacity supremum error one and
  departure supremum error two.
- The rare blocked-commodity prefix and throughput errors above were exact
  rational values.
- The five-to-three positive moment reduction and affine latent moment
  derivatives were checked exactly.
- The soft-min numerical example and delayed-feedback certificate inequalities
  were evaluated. Those floating-point evaluations support the displayed
  examples; the proofs are the analytic arguments above.

Primary sources actually opened/read:

1. Kruk, Lehoczky, Ramanan and Shreve, *An explicit formula for the Skorokhod
   map on [0,a]*, Annals of Probability 35 (2007), DOI
   `10.1214/009117906000000890`, arXiv `0710.2977`.
   https://arxiv.org/pdf/0710.2977
   Equation (1.1) gives the half-line reflection formula, and the introductory
   text gives its uniform-norm Lipschitz constant two. This anchors the
   reflection framework; (A1) is derived directly in arrival/service variables
   and does not need a multi-dimensional queueing theorem.
2. Bayer and Teichmann, *The proof of Tchakaloff's Theorem*, arXiv
   `math/0502473v2`, 2005.
   https://arxiv.org/pdf/math/0502473
   Theorem 1 and Corollaries 1–2 give positive finite representations of
   finite feature integrals. The finite-source elimination proof above is
   explicit and sufficient for the source-row use case.
3. Piccoli and Rossi, *Transport equation with nonlocal velocity in Wasserstein
   spaces: convergence of numerical schemes*, arXiv `1106.2555v3`.
   https://arxiv.org/pdf/1106.2555
   Hypothesis (H) on pages 2–3 requires spatially bounded/Lipschitz velocity and
   Lipschitz dependence on the measure in Wasserstein distance. Its whole-space
   transport/convergence results motivate the correct topology, but do not
   establish MetroFlow's FIFO node, finite-response state, boundary queue, or
   delayed development. The paper explicitly excludes generic dependence on
   pointwise density from its displayed (H).

SciSpace was used to locate reflection/queueing literature; Parallel retrieved
primary reflection and transport texts. Titles and abstracts were discovery
evidence, not premises substituted for proofs. No world-first or new strong
no-go claim is made.

## 9. Precise remaining obligations and theoretical handoff

1. **Actual native active-domain map:** determine class/movement support
   boundaries and receiving-space gate margins along the needed scenario.
   The inequalities above are derived; those scenario-dependent values are
   unresolved and no native run was attempted.
2. **Eligibility coupling:** establish (A6) for the chosen continuous phase
   reconstruction, or a finite event/transversality certificate for atomic
   native readiness. At network level, close the upstream-departure transfer
   term by a causal route graph, positive delays, or an explicit gain bound.
3. **Multi-sender node stability:** derive exact finite-stage constants for the
   source progressive allocator, including ties and threshold arithmetic.
   The single-sender bound (A5) and zero-supply counterexample are complete.
4. **Behavioral sufficiency:** map original purpose/class/information and future
   route semantics to candidate quotient states and test the equal-transition condition. If it fails,
   retain the distinguishing variable or state the revised behavior model.
5. **Moment consumer list:** choose a finite feature space from actual consumers,
   check generator invariance or compute bounded consumer residuals. Moment matching alone
   is not a dynamic-equivalence claim.
6. **Soft-min scientific choice:** determine whether the class target is a
   preference or an inviolable constraint. (B1) is admissible only as the
   corresponding explicit new closure. It does not regularize the FIFO node.
7. **Accessibility/development transfer:** identify observables, travel-time
   inverse margins or bounded kernels, lag history, and actual gains. The local
   feedback example provides a calculable criterion, not empirical calibration.
8. **Complexity calibration:** retain `J_sigma`, feature count, error residuals,
   and finite-time gains in any resource/accuracy estimate. No 8 GiB/7200 s,
   24 h, original-city accuracy, or original V03 acceptance conclusion follows
   from this author pass.

The usable theoretical advance is that altered composition and altered
capacity can be coupled quantitatively, with explicit restorative conditions,
while a separate behavioral reconstruction route states the stronger model
assumptions that would be needed for bounded state size. Original demand,
conservation accounting, finite information, finite response, and lagged urban
feedback remain the scientific targets.
