# R8 independent review: finite-response causal probe upgrade

Date: 2026-11-23.
Reviewer: /root/fifo_theory_review, one narrow independent pass.
Primary verdict: **proved as written**, within the explicitly stated positive,
spatially homogeneous, fixed-field, exact-probe and known-forcing assumptions.
**No material defect found in the new derivation or its stated implementation
claims. The newly identified physical-prior comparison gap is constructively closed.**

This is a review of the NEW upgrade only. The unchanged old FIFO-extension proofs
were not reopened. The earlier R6 proof verdict remains valid; it did not establish
that the old physical example improved prediction over all already known physical
speed bounds. The new comparison corrects that concrete scope/interpretation gap.

## Frozen review inputs

Repository:
 /home/cosmosapjw/worktrees/urban-traffic-v03-origin-validation-20261123

Author freeze received before reading the new source. Verified SHA256:

| File | SHA256 |
|---|---|
| docs/research/V03_FINITE_RESPONSE_PROBE_UPGRADE_20261123.md | e570e9ee34a7ee3f9dc0a3393dd8c80ed6d89f9b931a32aca2171e56b1829148 |
| src/metroflow/v1/finite_response_probe_certificate.py | 9621fa474a0ef0d647f8fb10fdb33fa361427b59a8fdeedda9b680916b5f1903 |
| tests/research/test_v03_finite_response_probe_20261123.py | bcbee4a6e4e6645f1fd387f8f069f5a133cd98add00a350e1d1ac2ac56bd2ed5 |
| artifacts/v03_origin_validation_20261123/R8_response_probe_experiment.py | a11609ae0e59b11db43852e25075cec28e545015a033da0d159f53a89530be84 |
| artifacts/v03_origin_validation_20261123/R8_response_probe_experiment.json | db5b5dc1a771b9bb4fc6e197cb07047461796b44d31b94b62aae55aeb62e619e |

Read the new raw experiment/test logs and exits. JSON/log summaries agree, and
the experiment's before/after input hashes match the frozen files.
Source, tests, proof, native code and runners were not modified.

Applicable AGENTS.md and original-intent watchdog were already read in the
preceding bounded task; their protected scientific/native contracts remain active.

## Normalized claim and dependency chain

For known tau>0, 0<a<=b, a<=v(x)<=b and a<=V(s)<=b, let
tau*v'=V-v in one spatially homogeneous fixed traffic context. A completed,
exact matched passage provides T=u-x>0 and L=integral[x,u] v, with
a<=L/T<=b. Delivery must occur by decision d>=u.

1. The passage integral bounds v(u) using the backward response kernel.
2. Known forcing bounds propagate that interval through d-u and future time.
3. Integrating the resulting positive extremal speed fields bounds future
   passage distance and, by monotone inversion, duration/arrival.
4. Comparing those arrival bounds gives robust route dominance.
5. The manufactured example separates observed history from unobserved future
   forcing, and improves over the complete global-speed-only baseline.

These are internal derivations. No unchecked external theorem or new literature
claim is needed. Broad literature review was outside this narrow task.

Units: x,u,d,T,tau,h seconds; L and future length ell metres; a,b,V,v m/s.
Alpha, T/tau and all exponential arguments are dimensionless.

## Independent mathematical reconstruction

### The old physical-prior comparison is a real gap, not an old theorem failure

With Gamma=b/a, known speed bounds already imply duration<=ell/a. For any
completed probe of that same link/population and a future t>=d>=u,

    U_Gamma(t)-t = T+(Gamma-1)*(t-x)
                 >= Gamma*T >= Gamma*ell/b = ell/a.

Taking a minimum over such probes preserves the inequality. Past completion
therefore cannot tighten the future duration upper beyond ell/a through this
particular Gamma construction. This does not refute sharpness in the larger
declared Gamma-function class. The new document correctly retracts the stronger
information-gain interpretation of the old example.

### Backward kernel and state information

Writing the solution backward from the observed exit gives

    v(x+s)=exp((T-s)/tau)*v(u)
            -(1/tau)*integral[s,T] exp((r-s)/tau)*V(x+r) dr.

Integrating over s and exchanging the integrals yields

    L=A*v(u)-integral[0,T] (exp(r/tau)-1)*V(x+r) dr,
    A=tau*(exp(T/tau)-1).

The nonnegative kernel has total mass A-T. Thus, with m=L/T and alpha=T/A,

    alpha*m+(1-alpha)*a <= v(u) <= alpha*m+(1-alpha)*b.

A>T>0 gives 0<alpha<1. Because m is itself in [a,b], these convex bounds lie in
[a,b]. The sign, integration factor, kernel mass and units all agree.
The exact observed exit u is essential: an interval's upper endpoint must not
silently be substituted for an exact passage time. The new CompletedPassage
contract explicitly requires exact matched entry/exit, so that substitution
is not being made.

### Delivery and future passage

Forward response from u to a future s gives

    w_minus(s)=a+alpha*(m-a)*exp(-(s-u)/tau),
    w_plus(s)=b-alpha*(b-m)*exp(-(s-u)/tau),

with w_minus<=v<=w_plus and both fields in [a,b].
Their integrals over [t,t+h] are exactly the displayed Q_minus and Q_plus.
The derivative with respect to h is positive, at least a, and each integral
starts at zero and increases without bound. Their roots are unique and obey

    ell/b <= root(Q_plus) <= true_duration <= root(Q_minus) <= ell/a.

When a<m<b, tau and t-u are finite and positive as specified, both memory
coefficients are positive. Both physical endpoints improve strictly in real
arithmetic. The explicit warning about floating underflow is appropriate.

The positive extremal fields are fixed functions of absolute time, so their
arrival maps are cumulative-distance inverse compositions and are FIFO.
Fixed-field composition is therefore legitimate. This proof does not assert
that route choice of finite demand leaves the traffic field unchanged.

Limits are consistent: long delay/forecast or tau->0 removes the observation's
memory; tau->infinity at fixed clocks produces both durations ell/m; a=b gives
the exactly known constant-speed passage.

### Actual endpoint witnesses for the chosen example

For tau=10, T=5, L=10, [a,b]=[1,3], constant forcing a or b during the observed
passage requires entry speeds

    1+0.5/(1-exp(-0.5)),
    3-0.5/(1-exp(-0.5)),

respectively. Both lie in [1,3]. Continuing their respective forcing through
decision and future time realizes the corresponding bounding speed field.
Hence the chosen example's extremal durations have valid physical histories.
The document correctly avoids generalizing this fact to global sharpness for
all possible probes.

## Exact route discrimination

The new example uses only the completed 10m passage from x=10 to u=15, delivered
at d=16, known tau=10 and [1,3]. A future 10m traversal in A is compared with a
separately certified 14m constant-2m/s route B.

Before source freeze, an independent Fraction/Taylor-remainder calculation gave
decision-speed endpoints approximately

    [1.6974007627801535, 2.3025992372198467] m/s,

and enclosed the two duration roots in

    [4.11801149, 4.11801150] s,
    [6.62243855, 6.62243856] s.

These are independently certified rational root brackets for the analytic example,
not a claim that the module's binary64 bracket endpoints are directed intervals.

The decisive exact inequality is

    Q_minus(16,7)
      =7+5*exp(-0.1)*(1-exp(-0.7))/(exp(0.5)-1)
      >7+17010/5057
      =52409/5057 >10.

Independently checked ingredients:

- exp(-0.1)>9/10.
- exp(0.7)>389/200 from its first three positive Taylor terms.
- exp(0.5)<2849/1728<33/20 using an upper geometric bound on the Taylor tail.
  The author's alternative, slightly looser tail argument to 33/20 is also valid.

Thus A's analytic worst-case duration is strictly below B's exact 7 seconds.
With only global speed information the upper-minimizer is B (A upper 10);
with the completed-probe response information it is A. For the allowed true
field v=V=2 in A, actual durations are 5 and 7 seconds. The baseline's actual
regret is 2 seconds and the upgraded choice has robust zero regret among these
two declared legal routes. No numerical rounding assumption is needed for the
strict decision.

## Implementation and experiment audit

The implementation corresponds to the analytic chain:

- CompletedPassage enforces finite values, positive matched duration/length,
  context/kind and exit-before-delivery.
- ResponseProbeCertificate checks context, delivery by decision, positive tau,
  positive ordered bounds and mean-speed compatibility.
- The z/expm1(z) form is stabilized for large z, and the continuous z->0 limit
  is used for ratio underflow.
- Forward response and distance integration use nonnegative convex forms.
- Bisection starts from the known [ell/b,ell/a] bracket; failure to resolve the
  requested tolerance raises ArithmeticError.
- The result is explicitly named NumericalDurationBounds and documented as
  approximate binary64 evaluation. The theory and exact route discriminator
  supply the mathematical guarantees; no general directed-rounding certificate
  is claimed.

The forcing/initial bounds remain a caller-certified physical input through all
queried exits. The new API has no numerical horizon field that could independently
verify this physical validity interval. This is a stated applicability premise,
not something sparse matched observations prove. Same-context semantics and
fixed-field comparisons also remain external inputs.

The experiment passes the measured past integral to the predictor. In the 24
future-switch cases, the future target appears only in the separate actual-field
oracle, not in the predictor. The 60 constant cases use observed mean speed via
probe length, not an additional future velocity input. The declared 84 rows and
120 high-precision bound-root comparisons agree with the inspected loops.

The author's receipts are 11 pytest passes and experiment exit 0. They were read,
not rerun or counted as this reviewer's execution. Their displayed maximum
9.215140108950740790481086699e-12s difference is a finite numerical comparison;
it is not promoted to a universal floating error bound.

## Actual independent executions

Only reviewer-owned artifacts were created under artifacts/v03_origin_validation_20261123.

1. Before source freeze:

       PYTHONDONTWRITEBYTECODE=1 python3 artifacts/v03_origin_validation_20261123/R8_independent_response_probe_example.py

   Exit 0; INDEPENDENT_RATIONAL_EXAMPLE_PASSED. Fraction-only Taylor remainder
   bounds establish the state interval, independent root brackets and exact
   dominance above. The log's PENDING_FREEZE field records the stage at execution;
   it is not an unresolved status after the subsequent frozen-source review.

2. After freeze:

       PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 artifacts/v03_origin_validation_20261123/R8_independent_response_probe_runtime.py

   Exit 0; INDEPENDENT_RATIONAL_RESIDUAL_CHECKS_PASSED.
   Observed wrapper wall time 0.21104726401972584 seconds.

   A separate Fraction oracle bounds exp using positive Taylor sums, a geometric
   remainder and rational inversion. It does not reuse the implementation's exp,
   expm1 or distance evaluator. Exact residual signs at each supplied numeric
   endpoint plus/minus 2e-11s establish proximity to the unique analytic root.

   - All 120 stored constant-case numerical root endpoints were checked.
   - 12 fresh runtime cases with tau=3,10,40 and endpoint/interior observed means
     were checked, covering 24 newly computed roots.
   - One additional absolute-clock-shift case was checked, covering two roots.
   - A query before the decision was rejected.
   - All five frozen input hashes, before/after source identities and raw JSON/log
     summary equality were verified.

The second execution establishes numerical accuracy in these stated finite cases.
It does not turn the binary64 return type into formal interval arithmetic.

Evidence files:
- R8_independent_response_probe_example.py / .log / .exit
- R8_independent_response_probe_runtime.py / .log / .exit
- R8_independent_response_probe_review.md

No Cargo, native execution, heavy run, whole-repository CI, source mutation,
new child review or literature campaign occurred.

## Obligation matrix and final disposition

| Obligation | Status |
|---|---|
| Correct physical-prior baseline comparison | passed, derived |
| Backward-integral sign/kernel/endpoint interval | passed, independently derived |
| Causal delivery propagation | passed, independently derived and code inspected |
| Positive distance roots and global nesting | passed, derived |
| FIFO of bounding arrival maps | passed, derived |
| Particular extreme-history admissibility | passed, derived |
| New information actually changes route selection | passed, exact strict inequality |
| Approximate implementation scope disclosed | passed |
| New numeric values vs independent rational residuals | passed in the stated finite range |
| General native forcing certificates and matched-probe instrumentation | unresolved integration input, outside this proof |
| General queue/spillback or finite-demand field invariance | outside scope |
| Unchanged prior FIFO theorems | not re-reviewed |
| General formal floating interval certification | not claimed |

Material findings: none. No source repair is required for this new result.
The identified scientific comparison gap is closed by a constructive response-memory
mechanism and a strict example relative to the full physical baseline.

Strongest safe conclusion: exact causal matched-passage information plus known
finite-response physics can supply genuine additional future route information
over positive global speed bounds, in the stated homogeneous fixed-field regime.
This is derived theory, with the implementation numerically checked in a finite
range and the featured route decision proved independently of floating rounding.

Drift watchdog: ALIGNED_WITH_OPEN_OBLIGATION. The result advances the original
mesoscopic finite-response -> causal information -> explainable routing objective.
Native demand, representation, FIFO, wire format, dt, budgets, runners and V03
acceptance remained unchanged. No city/24-hour empirical credit follows.

Skill context: PhysMath Research Loop 1.3.0 R6 and integrated finite-review policy;
mathbox proof-audit general logic, computation and source obligations. Already-read
unchanged skill instructions were reused. One narrow independent pass completed.
No further review is required or initiated by this report.
