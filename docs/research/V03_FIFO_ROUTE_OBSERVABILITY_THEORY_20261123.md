# V03 causal FIFO route observability: constructive arrival envelopes

Date: 2026-11-23. Base: 78d5e7e7e52e4db618a32ce3eca2e71f01b2433c.
Branch: research/v03-origin-validation-20261123.

## R2–R3: original motivation, actual gap, and reused results

The original active-mesoscopic idea connects mass-preserving interactions and
finite-response traffic to inspectable legal-route costs. The current V1
contracts preserve causal observation delivery. They do not identify an actual
future journey time by adding conditional link means. Sources:
docs/v1/r01/INFORMATION_KO.md, docs/v1/r02/ROUTING_KO.md, and
src/metroflow/v1/observations.py.

Native service events carry the original journey birth moment. An internal
passage's clock minus that moment is not its local link residence time. The
event-incidence snapshot also counts repeated passages. No matched link-entry/
exit probes are fabricated from those fields.

The 2026-11-22 quantile/source-index and dynamic-age loops already derive FIFO
generalized inverse service clocks, right-censored delays, and fixed-source
service dominance. The previous moment-envelope loop derives sharp mass/
moment/support stop-loss envelopes. These distinctions are reused, and none
of these old theorems is relabelled as new.

The present background-theory upgrade is constructive causal observation
extension: sparse matched boundary-passage observations plus a physically
justified expansion bound yield a class of admissible future arrival maps,
sharp functional envelopes, and a route/regret certificate. This closes a
specified information deficit without point predictions fabricated from
completed-population means.

Classical ingredients are attributed explicitly:

- E. J. McShane, Extension of Range of Functions (1934), Theorem 1, p. 838:
  extremal Lipschitz extensions from metric cones.
  https://www.ams.org/journals/bull/1934-40-12/S0002-9904-1934-05978-0/S0002-9904-1934-05978-0.pdf
- Brian C. Dean, Shortest Paths in FIFO Time-Dependent Networks: Theory and
  Algorithms, Section 2: nondecreasing arc arrival maps, path composition and
  FIFO shortest-path formulations.
  https://people.csail.mit.edu/bdean/tdsp.pdf
- Shortest paths in a network with time-dependent flow speeds (2000),
  model/non-passing travel-time/algorithm sections: integrate time-dependent
  speed over distance and use a Dijkstra variant.
  https://www.sciencedirect.com/science/article/pii/S0377221799000351

Primary text was retrieved with Exa and Parallel; SciSpace cross-checked the
bibliography. Retrieval scope and actual CAS output are recorded in
artifacts/v03_origin_validation_20261123/R2_theory_sources.json.
This is an explicit in-project upgrade, not a global novelty claim.

## R4: three concrete routes and selection

1. Frozen additive means: let \(E_1(t)=t+1\), and let \(E_2(t)=1+100t\)
   for \(0\le t\le1\), then \(E_2(t)=t+100\). Both maps are FIFO.
   Link costs sampled at zero sum to two seconds; the composed route exits
   at 101 seconds. This exact counterexample rejects reconstruction of actual
   route time, not the existing explicitly labelled behavioral closure.
2. Full cumulative boundary inversion: matched cumulative inflow/outflow and
   FIFO recover actual passage clocks, but journey-birth moments do not supply
   those local boundary observations. The earlier inverse-clock theorem remains
   valid; alone it does not close the sparse causal-information gap.
3. Directed FIFO extension, selected: delivered matched-passage intervals plus
   a declared expansion bound construct extremal maps and propagate their
   uncertainty along legal paths. Propositions 1–3 complete this route.

## Definitions and physical scope

Time is in seconds, length in metres, speed in m/s. Boundary labels may be
ordered vehicle-equivalent mass labels. No probability, stationarity,
route independence, equilibrium or natural units is assumed.

Fix a traffic field and an ordered non-overtaking boundary relation on one
directed link and one explicit vehicle/entry population. Its arrival map
\(E(t)\) is the exit clock of entry clock \(t\). A probe identifies the same
boundary label's entry \(x_i\) and exit interval \([\ell_i,u_i]\).
It is not a conditional completed mean. Batch/atomic data qualify only if
that ordered label and its entry are actually matched.

All probes used at decision \(d\) obey
\[
0\le x_i\le\ell_i\le u_i\le s_i\le a_i\le d,
\]
where \(s_i\) is the observation stamp and \(a_i\) its delivered clock.
The implementation rejects unavailable information, context mismatches and
a completed-mean measurement kind.

Fix a finite query domain \(I=[0,H]\), containing probes and \(d\).
Let \(\tau_{\min}\ge0\) be a physical travel-time floor and \(\Gamma\ge1\)
a certified expansion bound. Define
\[
\mathcal A_\Gamma=\{E:I\to\mathbb R:
E(t)\ge t+\tau_{\min},\
0\le E(t)-E(s)\le\Gamma(t-s)\ (s\le t),\
\ell_i\le E(x_i)\le u_i\}.
\]
The bound is a physical/model input; fitting finitely many past probes does
not certify future traffic. All required exits must lie in the interval
where the physical certificate holds.

Routing generally changes traffic. Comparisons use a fixed counterfactual
traffic field and population. Rerouting finite demand is not claimed to
preserve the maps.

## Proposition 1: sharp causal FIFO extension

With at least one probe, \(\mathcal A_\Gamma\) is nonempty if and only if
\[
u_i\ge x_i+\tau_{\min},\qquad
\ell_i\le u_j+\Gamma(x_i-x_j)_+\quad\text{for all }i,j.
\tag{1}
\]
When (1) holds, set
\[
L(t)=\max\!\left[t+\tau_{\min},
 \max_i\{\ell_i-\Gamma(x_i-t)_+\}\right],\qquad
U(t)=\min_i\{u_i+\Gamma(t-x_i)_+\}.
\tag{2}
\]
Then \(L,U\in\mathcal A_\Gamma\) and every admissible \(E\) obeys
\(L\le E\le U\). Both whole functions attain the bounds, so the result is
sharp in this declared function class.

### Proof

The physical floor at \(x_i\) makes the first condition necessary.
Monotonicity and the expansion bound give
\(E(x_i)\le E(x_j)+\Gamma(x_i-x_j)_+\), proving necessity of the second.

If \(t<x_i\), then
\(E(t)\ge E(x_i)-\Gamma(x_i-t)\ge\ell_i-\Gamma(x_i-t)\).
If \(t\ge x_i\), then \(E(t)\ge\ell_i\).
Together with the physical floor these prove \(E\ge L\).
The same cases using \(u_i\) prove \(E\le U\).

Each lower cone is nondecreasing and \(\Gamma\)-Lipschitz; the floor has
slope one. A finite maximum retains these properties because \(\Gamma\ge1\).
The finite minimum of the upper cones also retains them.
For \(t\le x_i\), \(u_i\ge x_i+\tau_{\min}\ge t+\tau_{\min}\);
for \(t\ge x_i\),
\(u_i+\Gamma(t-x_i)\ge t+\tau_{\min}\).
Thus every upper cone lies above the floor.

The oriented triangle inequality
\[
(x_i-x_j)_+\le(x_i-t)_++(t-x_j)_+
\]
and (1) imply
\[
\ell_i-\Gamma(x_i-t)_+
\le u_j+\Gamma(t-x_j)_+
\]
for every \(i,j,t\). Hence \(L\le U\).
At each probe, \(L(x_i)\ge\ell_i\) and \(U(x_i)\le u_i\); the opposite
inequalities follow from \(L\le U\). Therefore both extremal functions
satisfy every constraint, proving sufficiency and sharpness. \(\square\)

Sharpness does not assert that these endpoint functions are attainable by a
particular kinetic equation or coupled traffic network. Those physical
relations define a smaller admissible class.

### Missing expansion certificate

FIFO alone still supplies
\[
L_0(t)=\max[t+\tau_{\min},\max_{x_i\le t}\ell_i],\qquad
U_0(t)=\min_{x_i\ge t}u_i,
\]
where an empty upper minimum is \(+\infty\). Thus past-only measurements
leave the future upper unknown. The code represents this by None and
propagates it through route composition. No stop/spillback regime receives
an invented finite \(\Gamma\). With no probes, the lower floor survives and
the upper is unknown even when a finite slope is declared.

## Proposition 2: a finite-response physical certificate

Consider a spatially homogeneous fixed-environment field
\[
\tau_r\dot v(t)=V(t)-v(t),\quad \tau_r>0.
\]
Suppose the initial speed and prescribed target \(V(t)\) belong to
\([v_-,v_+]\), with \(0<v_-\le v_+<\infty\), throughout the physical interval
needed by every passage. Measurable bounded \(V\) and its absolutely continuous
solution suffice. For a link of length \(\lambda>0\),
\[
\int_t^{E(t)}v(s)\,ds=\lambda,\qquad
\tau_{\min}=\lambda/v_+,\qquad \Gamma=v_+/v_-
\tag{3}
\]
give a valid instance of Proposition 1 for covered entries and exits.

### Proof

The variation-of-constants solution is
\[
v(t)=e^{-t/\tau_r}v(0)+
 \int_0^t\tau_r^{-1}e^{-(t-s)/\tau_r}V(s)\,ds.
\]
Its nonnegative weights sum to one, so \(v_-\le v(t)\le v_+\).
The distance integral increases strictly with the exit clock. Where the
physical interval is long enough it has a unique exit, with
\(\lambda\le v_+[E(t)-t]\).

For \(t_2\ge t_1\), subtracting the distance equations gives
\[
\int_{E(t_1)}^{E(t_2)}v(s)\,ds=\int_{t_1}^{t_2}v(s)\,ds.
\]
Positivity implies \(E(t_2)\ge E(t_1)\), and the speed bounds imply
\[
(v_-/v_+)(t_2-t_1)
\le E(t_2)-E(t_1)\le(v_+/v_-)(t_2-t_1).
\]
This proves FIFO and the expansion certificate.
Where derivatives exist, \(E'(t)=v(t)/v(E(t))\). \(\square\)

This is a constructive restricted mechanism connecting finite response and
causal routing. It requires spatial homogeneity and a positive speed floor.
The native network can stop, queue, spill back, merge, or change under rerouting;
those cases require a separate certificate. A positive instantaneous sample
or configured free speed does not provide this guarantee.

## Proposition 3: route composition and robust regret

On the legal turn-expanded graph, each arc has nondecreasing enclosures
\(L_e\le E_e\le U_e\), all with arrival no earlier than entry, using information
delivered by the original departure decision. For a path
\(r=(e_1,\ldots,e_k)\), define the composed maps
\[
L_r=L_{e_k}\circ\cdots\circ L_{e_1},\quad
E_r=E_{e_k}\circ\cdots\circ E_{e_1},\quad
U_r=U_{e_k}\circ\cdots\circ U_{e_1}.
\]
Then \(L_r(t)\le E_r(t)\le U_r(t)\), by induction and monotonicity of each
next arc. Every evaluated entry must be inside its declared domain;
otherwise the implementation raises a domain error.

Let \(L_*=\min_r L_r(t)\), \(U_*=\min_r U_r(t)\), and choose a path \(\hat r\)
with finite upper \(U_*\). Minimizing the path inequalities and then using
\(E_{\hat r}\le U_*\), \(T_*=\min_r E_r\ge L_*\) gives
\[
L_*\le T_*\le U_*,
\qquad 0\le E_{\hat r}(t)-T_*\le U_*-L_*.
\tag{4}
\]
If one path's upper is below all competing simple-path lower bounds, that path
is optimal in every compatible fixed field. Cycles cannot improve FIFO arrival:
removing a cycle reaches the suffix earlier, and that suffix is nondecreasing.
Ties need not be unique.

Lower/upper optima can be computed separately by time-dependent Dijkstra.
A relaxation evaluates the relevant map at the current arrival clock.
This preserves the FIFO label-setting proof. The implementation does not assign
path-size probabilities or replace production R02 tie/expansion rules.

For independently selectable arc classes, choosing all lower or all upper
maps also attains path/optimum envelopes. Coupled traffic may prohibit those
simultaneous extremes; the enclosure and regret result remain valid.

## R5–R7: implementation and actual evidence

Implementation:
- src/metroflow/v1/fifo_route_observability.py: rational probe contracts,
  admissibility, sharp envelopes, unknown upper propagation, path composition,
  legal graph certificates, and a finite-response reference field.
- tests/research/test_v03_fifo_route_observability_20261123.py: exact formulas,
  causality/context/domain rejection, all 34 admissible integer maps in the
  4-clock fixture, finite-response integrals, 124 withheld passages, legal
  cycle and frozen-cost counterexample.
- artifacts/v03_origin_validation_20261123/R7_theory_experiment.py: reproducible
  experiment with exact fractions, source hashes and capture-time Git/dirty
  provenance. JSON and raw stdout are saved alongside it.

Actual commands from this worktree:

    PYTHONPATH=src:. python3 -m pytest -q tests/research/test_v03_fifo_route_observability_20261123.py

Result: 11 passed in 0.34s, exit 0. First execution was 10 passed / 1 failed
because the fixture incorrectly expected 50 grid maps. Direct counting is
\(2(2+3)+3(2+3+3)=34\), matching complete enumeration.
Only that expected count changed; no production formula changed.
R7_theory_tests_first.log preserves the failure. It is a fixture defect,
not a claimed behavioral RED or theorem refutation.

    PYTHONPATH=src:. python3 artifacts/v03_origin_validation_20261123/R7_theory_experiment.py

Result: EXACT_RATIONAL_REFERENCE_EXPERIMENT_COMPLETED, exit 0,
124 withheld passages, final measured wall 0.143555085s.
Exact hashes and source state are in its JSON.
A later Git commit with unchanged inputs does not invalidate these results.

### Exact finite-response physical experiment

Velocity knots are \((0,2),(20,3),(40,2),(100,2)\) in (s,m/s), and
\(\tau_r=2\) seconds. The declared forcing is \(V=v+\tau_r\dot v\).
Its one-sided values lie in \([19/10,31/10]\) m/s.
This is a manufactured exact solution of the stated finite-response ODE,
not an arbitrary linear arrival map, and not native V03 city evidence.

For lengths 5,10,20,30 metres, integrate piecewise-affine velocity exactly
and bracket each distance-integral root with rational bisection.
Final width is at most \(10^{-10}\) seconds; all comparisons are exact.

Candidate probe entries are 0,5,10,15 seconds. Only passages whose rounded-up
completion stamp plus one-second information latency is at most \(d=20\)
are admitted. Future entries \(20,20.5,\ldots,35\) are withheld.
The predictor receives only those delivered probes, \(\Gamma=31/19\),
the physical lower delay and declared query domain; it does not receive
future speed samples. All 124 withheld passages fall inside their envelopes.

At departure 20 seconds, a direct 10-metre link versus a legal 20+20-metre
detour produces the following arrival clocks:

| Quantity | Enclosure endpoints displayed approximately, seconds |
|---|---:|
| Direct predicted | [23.2258064516, 26.6813942905] |
| Detour predicted | [32.9032258065, 56.2142524713] |
| Actual direct | [23.4314575050666, 23.4314575051394] |
| Actual detour | [35.2786404499797, 35.2786404501106] |

The direct upper is 6.221831516 seconds below the detour lower.
The general certificate (4) gives a 3.455587839-second regret bound.
The stronger dominance comparison certifies zero regret among declared
simple paths; the test's legal return cycle cannot improve a FIFO path.

This resolves a concrete scientific observation blocker in the specified regime:
a causal route arrival guarantee can be constructed from valid matched
measurements without misidentifying conditional means, event incidences or
original birth ages as local traversal clocks.
It does not close native memory admission, instrument every native link, or
establish a full-city/24-hour route guarantee.

## Drift watchdog and remaining obligations

Preserved original intuition: finite-response traffic affects route choice
through an explainable and causally available cost construction.
Preserved current authority: production PacketNetwork, native f64/FIFO/wire,
demand, caps and R01/R02 behavior are unchanged.

Observed drift risk: repeated lineage-identity work can be mistaken for progress
on transport observables. The constructive correction is the theorem and exact
physical reference experiment above. A second risk is promoting a positive-speed
closure to the whole congested city. Unknown uppers and finite domains remain
explicit, and stopped/spillback native cases are outside the finite-Gamma claim.

Evidence status: author derivation complete; exact rational finite checks
executed; independent R6 proof/code review is arranged by the parent separately.
Production boundary-pair instrumentation and physical expansion certificates
for general native queues remain unresolved integration obligations.

Skill context used: PhysMath Research Loop 1.3.0 R2–R7 and its integrated
constructive/evidence policy; mathbox research-program plus program protocol;
mathbox computation-audit. No recursive review or native simulation was
launched by this theory worker.
