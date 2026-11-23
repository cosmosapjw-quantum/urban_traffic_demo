# MetroFlow: observer factorization, closed queries, and analytic transport marks

Date: 2026-11-23. Theory-only R4/R5 contribution, based on source HEAD
492e27618696df2514b088a64de450cf69746647. These are direct derivations and
source-conditioned constructions, not claims of literature novelty. No new
native implementation or city execution is included.

## 1. Passive historical observation without losing active completion history

The source anatomy distinguishes the prior complete road event trace from
same-tick sinks and from Journey ReceiptHistory. The prior last_events is
stored, cloned for external query, serialized, validated and charged to memory.
The new tick's sink tuples (tag, amount, end time) drive service/journey updates.
ReceiptHistory subsequently controls next-leg eligibility and stays active.

Let X contain all physical/service/journey states, active histories and control
inputs. Let O be the ordered detailed prior road trace. On successful
transitions write
\[
X'=F(X,u),\qquad O'=G(X,u).
\tag{O1}
\]
F includes the action of the newly produced sink projection of G. Thus (O1)
does not remove same-tick completion feedback. It only excludes the old O
from the physical value computation. Admission and validation are separate
predicates A(X,O,u), V(X,O) and can depend on O.

**Proposition O1 (lossless observer factorization).** Suppose e encodes every
admissible ordered trace, d(e(O))=O, and the compressed validator is
Vhat(X,o)=V(X,d(o)). Define
\[
\widehat T(X,o;u)=\bigl(F(X,u),e(G(X,u))\bigr).
\]
On transitions admitted and successful in both representations,
\[
(\mathrm{id},d)\widehat T
=T(\mathrm{id},d).
\tag{O2}
\]
Consequently their physical states and decoded detailed observations agree
after any finite common-admissible sequence.

**Proof.** Apply the decoder to the second component and use d e=id. The first
component has identical X,u, including the identical new sink projection. This
establishes one step, and induction establishes any finite sequence. Querying
h(O) becomes h(d(o)); no information is erased. If the same checkpoint header,
tuple order and writer are used, streaming those decoded tuples gives the same
byte sequence. This last conclusion is a conditional serializer identity, not
a claim that a new serializer was implemented or tested. QED.

Resource admission domains may improve after changing storage. Equation (O2)
does not assert identical failures, allocation sizes or guard outcomes. Any
validator that was implemented by direct Vec inspection must be adapted to
the decoded semantics. A decoder that silently changes time bits or ordering
does not meet the premise.

**Concrete payload target from old evidence.** The S07 input contains
14,432,257 old events, 64 bytes each, hence 923,664,448 payload bytes and
923,664,576 retained charged bytes. The same S08 last trace had timed-page
payload 464,781,312 bytes. Keeping that timed carrier persistent would change
payload by
\[
923{,}664{,}448-464{,}781{,}312
=458{,}883{,}136\ {\rm B}.
\tag{O3}
\]
This is a conditional payload difference from measured components, not a
measured new saving or a complete live-memory bound. Page descriptors, all
input/current/candidate owners, validation scratch and caches remain charged.
After the first internal tick of an advance call, the original call-input
trace and current trace can be distinct owners.

The current checkpoint event wire requires 8+64E-8Z bytes for E rows and Z
sink rows. Full legacy output therefore still writes all those bytes; streaming
reduces simultaneous materialization, not output volume. The current full-Vec
external road_events API still requires a full allocation if its contract is
retained. This route removes an observer-storage bottleneck, while the
composition and interval work must be addressed by other routes.

## 2. A criterion for exact physical summaries

Let mu be a finite positive marked measure. For a family of physical queries
psi_1,...,psi_m, define
\[
P\mu=(\langle\psi_1,\mu\rangle,\ldots,\langle\psi_m,\mu\rangle).
\]
The full state also retains any explicit finite-response variables, ordered
head metadata, event calendars and active histories needed by the controller.
Let A_a be a linear transport operator at a held control value a.

**Proposition Q1 (dual closure).** Suppose every control choice, event guard
and required observable depends on the retained state and P mu; all relevant
event resets are closed on that state; and
\[
A_a^*\psi_i=\sum_j M_{ij}(a)\psi_j
\tag{Q1}
\]
for every allowed operation/control. Then the projected transport closes as
\[
P(A_a\mu)=M(a)P\mu,
\tag{Q2}
\]
and the full hybrid transition has a deterministic projected transition.

**Proof.** The ith coordinate is
<psi_i,A_a mu>=<A_a^* psi_i,mu>=sum_j M_ij<psi_j,mu>.
Equal retained states therefore select equal controls and event durations.
Equation (Q2) preserves their projected equality, and closed resets complete
one event. Finite induction proves the hybrid statement. QED.

The infinitesimal version is generator invariance L_a V subset V for
V=span{psi_i}. Finite sums, route pushforwards, class marks and projections can
instead be treated by an indexed family of pullback queries, without requiring
a small finite-dimensional span. In that version the number of distinct
node/query pairs is part of the actual cost.

This criterion is sufficient, not a proof that MetroFlow has a small
autonomous moment model. It explains the exact route's missing performance
obligation: cheap expression storage alone is insufficient if evaluating its
consumer queries unfolds the same product.

**Explicit moment ambiguity.** On an age coordinate a [s], set
mu=(delta_0+delta_2)/2 and nu=delta_1, in units of one vehicle.
Both have mass1 and first age moment1 vehicle-second. The eligible amount
at threshold a>=1.5 s is 1/2 for mu and0 for nu. Therefore the eligibility
indicator is not determined by these two features. Retaining the actual
target/rank CDF, the needed indicator, or a controlled regularity class repairs
this example. The example does not rule out all finite closures.

For a fixed supported class with affine latent dynamics
dp/dt=r-lambda p, polynomial moments up to degree d obey
dm_k/dt=k r m_(k-1)-k lambda m_k. Thus they provide an actual invariant
feature space. Class heterogeneity, nonlinear route choices and FIFO eligibility
must be included separately; this does not turn arbitrary tag dynamics into
a finite polynomial system.

### Positive reconstruction and an explicit consumer residual

**Proposition Q2 (finite positive feature realization).** Let a finite positive
source measure have atoms theta_i and weights w_i. Choose m scalar features
phi_1=1,phi_2,...,phi_m, with each coordinate expressed in its own consistent
units. There is a positive measure on at most m of the source atoms with the
same feature integrals.

**Constructive proof.** With more than m positive weights, the feature vectors
v_i=(phi_1(theta_i),...,phi_m(theta_i)) are linearly dependent. Choose a nonzero
coefficient vector a with sum_i a_i v_i=0. Its first coordinate gives sum_i
a_i=0, so positive and negative coefficients both occur. Let
s=min_(a_i>0) w_i/a_i and replace w_i by w_i-s*a_i. All weights stay
nonnegative, at least one becomes zero, and every feature integral is unchanged.
Remove zero atoms and repeat finitely until at most m remain. QED.

This is a finite-source constructive instance of positive cubature, not a new
general cubature theorem. Bayer and Teichmann's primary proof provides the
broader measure-theoretic context: https://arxiv.org/pdf/math/0502473.

If a required scalar consumer has
g=sum_i alpha_i phi_i+r_g with |r_g|<=epsilon_g on the common source domain,
and source/reconstruction both have total mass M, then
\[
\left|\int g\,d\mu-\int g\,d\widehat\mu\right|
\le 2M\epsilon_g.
\tag{Q3}
\]
Indeed the matched feature contributions cancel and each residual integral is
at most M*epsilon_g. This gives an actual error term for a coupled stability
estimate. A support indicator for a rare blocked movement generally has no
small uniform residual on a stratum crossing that support boundary; it must
be retained or the physical operator must explicitly change.

Applying Q2 separately inside retained FIFO/behavior strata preserves their
order and mandatory support partition. Per-class/route indicators must be
included if they are not already fixed by the stratum. Keeping a small global
feature set while discarding those distinctions is not justified by Q2.
Maintaining Q1 or a controlled Q3 residual over evolution remains necessary.

## 3. Flux-weighted marks as a separate finite-response numerical model

### 3.1 The source operation that makes artificial cuts active

In v1_road.rs, characteristic (2410–2424) integrates a held target with bounded
acceleration/braking and exponential relaxation. motion (3082–3169) computes
its coefficients and class latent hazards. A service interval [a,b] then marks
every incoming part with source speed and latent at (a+b)/2 (3980–4002).
Receiving speed and latent use mass-weighted marks (4200–4253).

Even when adjacent intervals have the same composition and flux, merging them
changes midpoint marks. Exact algebraic storage may share their composition
but must retain the virtual original event cuts. The alternative below changes
the quadrature/mark model explicitly, while retaining the source finite-response
characteristics and conservation.

### 3.2 Held phase, flux, units and boundaries

Work inside one phase with a fixed source Motion and class hazard. Local time
is measured from that Motion's origin. Let a<b be inside this phase,
h=b-a [s], and let a service's actual emitted mass be M_e [veh].
Its uniform temporal flux is r_e=M_e/h [veh/s], with class shares theta_k.
Using actual emitted mass rather than blindly identifying it with a rate*h
product respects any declared endpoint/fraction convention.

Assume v0,target>=0, tau>0, acceleration and braking limits>0. The source
characteristic speed is v(t), and its cumulative distance is chi(t) [m].
For class k write lambda_k=r_k+nu_k>=0 [1/s] and initial latent p0_k in[0,1].
When lambda_k>0, p_inf,k=r_k/lambda_k and
\[
p_k(t)=p_{\infty,k}+(p_{0,k}-p_{\infty,k})e^{-\lambda_k t}.
\tag{E1}
\]
When lambda_k=0 the source latent is constant p0_k.
Actual changes of composition, target, hazard, flux or node constraint still
bound phases. They cannot be erased merely to reduce descriptor counts.

### 3.3 Exact integration and subdivision invariance

Define the outgoing speed moment and class latent moments by
\[
J_v(e)=r_e\int_a^b v(t)\,dt
=r_e[\chi(b)-\chi(a)],
\tag{E2}
\]
\[
J_{p,k}(e)=r_e\theta_k\left[
p_{\infty,k}h+
(p_{0,k}-p_{\infty,k})e^{-\lambda_k a}
\frac{1-e^{-\lambda_k h}}{\lambda_k}\right].
\tag{E3}
\]
For lambda_k=0 use r_e theta_k p0_k h. Units are
[vehicle*m/s] for J_v and [vehicle] for J_p.

**Proposition E1 (conservative, subdivision-invariant mark transport).**
For fixed source characteristic, class composition and flux, the moments
(E2)–(E3) are additive under any finite subdivision of [a,b]. With survivor
mass M0 and speed v0_surv, and survivor class masses M0k/latent p0k_surv,
\[
v_{\rm new}=\frac{M_0v_{0,\rm surv}+\sum_e J_v(e)}
{M_0+\sum_eM_e},
\qquad
p_{k,\rm new}=\frac{M_{0k}p_{0k,\rm surv}+\sum_eJ_{p,k}(e)}
{M_{0k}+\sum_eM_e\theta_{e,k}}
\tag{E4}
\]
are independent of these artificial subdivisions whenever their denominators
are positive. Empty receiving states use the separately specified zero-mass
convention. Vehicle, birth, person and cargo amounts are unchanged.

**Proof.** Integrals over disjoint subintervals add, as do emitted masses.
Equations (E2) and (E3) are their elementary antiderivatives. Hence both
numerators and denominators in (E4) remain unchanged. Every coefficient in the
time-weighted mixture is nonnegative, so the new speed lies in the convex hull
of survivor/source speeds, and latent stays in[0,1]. Marks do not alter mass or
the attached additive attributes. QED.

For a single relaxation p(t)=P+(p0-P)e^(-t/tau), write
J(p0,h)=r[P h+(p0-P)tau(1-e^(-h/tau))].
Using the updated p(s) at the split gives
J(p0,s)+J(p(s),h-s)=J(p0,h). A Wolfram symbolic evaluation returned zero for
this residual and for the antiderivative residual. They check the formulas,
not native integration.

The clipped speed also has a closed antiderivative. Put
d=target-v0, l=accel if d>=0 else brake, sigma=sign(d),
t_s=max(|d|/l-tau,0), v_s=v0+sigma*l*t_s.
Before t_s, v(t)=v0+sigma*l*t; afterward,
v(t)=target+(v_s-target)exp(-(t-t_s)/tau).
Integrating the affine and exponential pieces gives exactly the source chi.
Thus (E2) reuses the existing analytic characteristic rather than introducing
instantaneous equilibrium or a new road-speed law.

For uniform flux, the time moment r integral_a^b t dt=M_e(a+b)/2, so source
linear time/hold ledgers already have the exact same midpoint integral.
Waiting terms max(t-ready,0) require splitting at readiness if crossed.
Nonuniform flux requires its actual weighted integral; one midpoint or an
unweighted time average is not the same construction.

### 3.4 Difference from the existing kernel and local error

For a C2 mark g on one phase, midpoint quadrature obeys
\[
\left|r\int_a^b g(t)\,dt-rh\,g((a+b)/2)\right|
\le\frac{r h^3}{24}\sup_{[a,b]}|g''(t)|.
\tag{E5}
\]
Proof: expand at the midpoint with integral/Taylor remainder. The odd linear
term integrates to zero, and (1/2) integral_(−h/2)^(h/2) s^2 ds=h^3/24.
For the clipped speed, split at saturation/relaxation transitions before
applying this C2 statement. For (E1), the curvature bound is explicit:
|p0-p_inf| lambda^2 exp(-lambda*a).

With v(t)=1-exp(-t) m/s, constant flux1 vehicle/s and [0,2]s:
\[
J_{\rm exact}=1+e^{-2}=1.1353352832366127,
\]
\[
J_{\rm split-mid}=2-e^{-1/2}-e^{-3/2}=1.1703391801389367,
\qquad
J_{\rm merged-mid}=2-2e^{-1}=1.2642411176571154.
\]
All moments have units vehicle*m/s. The two midpoint choices differ by
2e^(-1)(cosh(1/2)-1)=0.0939019375181786 despite identical total mass/flux.
The integrated choice is unchanged by splitting. It is not byte-identical or
numerically identical to either midpoint choice.

For several phases the local discrepancy is bounded by summing their (E5)
terms, with class-specific rates for latent. Converting a moment error into
a receiving mean requires a positive receiving mass denominator. Transmitting
it into later capacity/arrival differences requires the coupled support-aware
stability assumptions in the companion derivation. No global city error
or V03 equivalence is inferred from this local estimate.

The constructive gain is that one held phase needs one analytic speed integral
and at most one latent integral per supported class, while composition may
remain a shared expression. Genuine phase counts and label-dependent external
outputs remain explicit costs.

## 4. How the routes address the complete chain

Observer factorization addresses retained history, operator transport addresses
the duplicated composition construction, behavioral quotient addresses repeated
physical queries, support-aware measures address state-resolution growth, and
integrated marks address a discretization-induced reason to retain artificial
cuts. They are complementary proposals, not interchangeable names.

For any proposed combination, charge the union of dependencies reachable from
input/current/candidate roots, active journey histories and requested observers.
Also count descriptor owners and all query caches. Source roots must not capture
an entire old WorldState. A small new header can otherwise keep a large old
state alive. Full export or per-tag policy evaluation remains charged when
requested. No proof here assumes a uniform bound on ancestry, event count,
class/suffix diversity or consumer feature dimension.

The next discriminating theoretical data are actual source-root reuse, true
control/event knots, class/suffix group support and distinct pullback queries.
The current receipt does not measure these, so a resource-completion prediction
for 24 hours remains unresolved. The original scientific target and resource
thresholds remain unchanged.
