# R6 independent FIFO arrival-map proof and implementation review

Date: 2026-11-23.
Reviewer: fresh native subagent /root/fifo_theory_review, bounded independent pass.
Scope: the frozen FIFO observability claim, research module, scoped tests, raw
manufactured experiment, and source provenance. No recursive delegation.
Primary verdict: **proved as written** under the stated finite-domain, fixed-field,
causal matched-probe, and certified-expansion hypotheses.
**No material mathematical or implementation defect found in this scope.**

This verdict concerns Propositions 1–3 and their research implementation. It does
not certify native V03 travel times, unknown future traffic fields, stop/spillback
expansion bounds, boundary instrumentation, whole-city scaling, or 24-hour acceptance.
The author's 11-test receipt was read, not independently rerun or relabelled.

## Exact reviewed identity and authority

- Repository: /home/cosmosapjw/worktrees/urban-traffic-v03-origin-validation-20261123
- Observed review-start HEAD: d415c55b66f20f02adeb78c0af690216c2bc778b.
  The scientific bindings below are file identities, not a claim that all artifacts
  had already been committed at that HEAD.
- Proof: docs/research/V03_FIFO_ROUTE_OBSERVABILITY_THEORY_20261123.md
  SHA256 0f03c9ff12000102dcdd8d4e264288dd931ddff1bc656d56740ce42894b52785.
- Implementation: src/metroflow/v1/fifo_route_observability.py
  SHA256 eb94236bfb5b0d0e66e9f4035aa71f117de343001ac92f1c6b94e0308e62ed58.
- Author tests: tests/research/test_v03_fifo_route_observability_20261123.py
  SHA256 456a3e58f33fe69b6404f2a45116a6d208f0259f5edbec1c03b03ff63561b4e2.
- R7_theory_experiment.py:
  189b4f6b31eaae6a2729ab2dc541ac0e1b02ea2777051804818266c120b4ae74.
- R7_theory_experiment.json:
  47246413435c187925b43a8399b6cf133f39c993396672e072159e63a05ce3a7.
- R7_theory_experiment.log:
  3bb6e8534ba53a7c10a6bbb3b546a466df65a6e3ed3a76dd73278ed6cf1a0073.
- R7_theory_tests.log:
  a1be914db631b340553d5b4ca73e313ec3ce1b006329c82674be2b42fb04cb27.
- R2_theory_sources.json:
  ca3f54df9d65d44a2f167c820122c69f68705b034abf8739c967755708ad92c3.

Read AGENTS.md and docs/research/METROFLOW_ORIGINAL_INTENT_WATCHDOG.md.
No nested AGENTS.md was present in the specific reviewed file ancestor directories
inside the repository. Production/test/proof inputs were not modified.
Source hashes also matched the capture-time identities in the experiment JSON.

## Normalized claim card

For finite nonempty matched observations (x_i,[ell_i,u_i]), on I=[0,H], with
tau>=0 and Gamma>=1, consider real-valued nondecreasing Gamma-Lipschitz
E satisfying E(t)>=t+tau and ell_i<=E(x_i)<=u_i.
The claim is exact nonemptiness iff

    u_i >= x_i+tau,
    ell_i <= u_j+Gamma*max(x_i-x_j,0) for every i,j.

The claimed functions are

    L(t)=max(t+tau, max_i [ell_i-Gamma*max(x_i-t,0)]),
    U(t)=min_i [u_i+Gamma*max(t-x_i,0)].

They are whole-function extrema in this declared abstract class.
The class does not additionally demand realization by a kinetic equation or by
a coupled native network. Physical realizability of its endpoints is not claimed.

A spatially homogeneous positive finite-response field gives a sufficient
physical certificate Gamma=v_plus/v_minus and tau=lambda/v_plus.
Monotone composition on covered entry domains gives path and optimum enclosures,
with regret at most U_star-L_star for an upper-minimizing legal path in one fixed
counterfactual field. Arcwise independent classes are needed only for simultaneous
attainment of route extrema, not for the enclosure inequality.

Units: t, x, ell, u, tau, relaxation time are seconds; lambda metres; v m/s;
Gamma dimensionless. No probabilistic or stationary premise is being inserted.

## Dependency graph and independent reconstruction

1. Causal matched boundary observations -> legitimate interval constraints.
   This is a measurement/input contract, not a deduction from journey birth ages.
2. Monotonicity + Lipschitz bound + physical floor -> necessary pairwise inequalities.
3. The cone extrema satisfy the same shape constraints and observations ->
   nonemptiness and global sharpness.
4. Positive target/initial bounds -> invariant speed interval -> unique passage
   root -> FIFO and the expansion ratio.
5. Edge enclosure + monotonicity + covered domains -> composed path enclosure.
6. Minima over legal paths + a selected finite upper -> optimum and regret bounds.
7. Arrival >= entry + FIFO -> cycle removal and label-setting correctness.

Leaves 2–7 are internal mathematical arguments reconstructed below.
Leaf 1, physical certification, fixed-field comparability, graph legality, and
domain coverage are declared inputs. External papers supply attribution/context;
no missing external theorem is needed to make these proofs work.

### Feasibility and full-function attainment

For any E and i,j, if x_i<=x_j, FIFO gives E(x_i)<=E(x_j); if x_i>x_j,
the expansion bound gives E(x_i)<=E(x_j)+Gamma*(x_i-x_j).
This yields the pairwise condition, while the floor yields u_i>=x_i+tau.

Independently of the proof's triangle-inequality presentation, inspect the
candidate functions directly at a probe x_i. Each lower cone indexed by j obeys

    ell_j-Gamma*max(x_j-x_i,0) <= u_i,

by the pairwise condition with indices j,i. The floor at x_i also lies below u_i.
Thus L(x_i)<=u_i, and its i-th cone ensures L(x_i)>=ell_i.

Likewise every upper cone at x_i is >=ell_i by the pairwise condition with
indices i,j; the i-th upper cone equals u_i. Thus ell_i<=U(x_i)<=u_i.
Each upper cone stays above the floor: for t<=x_j use u_j>=x_j+tau,
and for t>=x_j use Gamma>=1.

For s<=t, every cone has increment in [0,Gamma*(t-s)]; the same is true of
its finite max or min. The floor has slope 1 and hence is allowed.
Therefore L and U themselves are admissible. Applying the cone inequalities
to any admissible E gives L<=E<=U. This proves both necessity/sufficiency and
whole-function attainability without a sampled or numerical proof substitute.

Duplicate probe times reduce to compatible intersecting intervals.
With no probes, t+tau is admissible and arbitrarily large vertical shifts remain
admissible, so a finite upper is genuinely unavailable even with finite Gamma.
For Gamma unknown, FIFO-only constraints and the stated L0/U0 are valid;
+infinity is an upper supremum marker, not a real-valued endpoint function.

A useful causal consequence, not a defect: for future queries t>=d with all
probe exits delivered by d, L(t)=t+tau. If Gamma is finite and probes exist,

    U(t)=Gamma*t+min_i(u_i-Gamma*x_i).

Past completed probes sharpen the future upper here; their lower cones cannot
exceed the physical floor at or after the decision. The experiment uses exactly
this information content and makes no stronger lower-prediction claim.

### Finite-response physical certificate

The variation-of-constants weights are nonnegative and sum to one, giving
v_minus<=v(t)<=v_plus. Positive velocity makes the distance primitive strictly
increasing. If the physical time interval covers the required passage, its
root is unique. Comparing the two equal-length passage integrals gives

    integral[E(t1),E(t2)] v = integral[t1,t2] v,

so FIFO follows, and bounding both integrals gives

    (v_minus/v_plus)*(t2-t1) <= E(t2)-E(t1)
                              <= (v_plus/v_minus)*(t2-t1).

The delay floor is lambda/v_plus. Piecewise-affine continuous v and bounded
one-sided jumps in V=v+tau_r*v' satisfy the ODE almost everywhere.
Nothing here derives a positive floor for stopped, spillback, merging, spatially
inhomogeneous or demand-dependent native traffic.

### Routes, finite domains and label setting

Induction uses monotonicity at each actual/intermediate argument to sandwich
the next arrival. Minima then give L_star<=T_star<=U_star and the displayed
regret bound. Removing a cycle does not delay entry to the remaining suffix;
FIFO prevents an earlier suffix entry from worsening arrival. Zero-time cycles
and ties are harmless; strict label improvement prevents repeated zero-cycle
relaxation. The heap implementation evaluates maps at the current label and
retains an upper-minimizing path.

The domains constrain ENTRY clocks, not the returned exit clock. Exits can
legitimately exceed an arc's own entry horizon. Every next evaluated entry
must lie in the next arc's certified domain. The code raises ValueError on a
queried domain exhaustion, including when only an upper label leaves that domain.
An irrelevant explored arc may cause a conservative error rather than an answer;
the implementation does not promise maximal partial-domain salvage.

As the theorem states, actual passages also need domain coverage. A propagated
None upper cannot by itself certify the actual downstream entry is inside a
finite domain. Reading a lower result in that case retains the theorem's
external actual-domain coverage premise. The implementation cannot infer that
physical premise from absent upper information. No claim of globally certified
routes beyond supplied domains was admitted in this review.

All information must have been delivered by the original departure. Per-probe
clock ordering and context are enforced at construction; route composition and
graph certificates reject later envelope decisions. Legal turn-expanded graph
construction and semantic population matching remain caller inputs, as stated.

## Obligation matrix

| Obligation | Status | Decisive evidence |
|---|---|---|
| Proposition 1 necessity/sufficiency | passed, derived | Direct probe-index reconstruction above |
| Whole-function L/U attainment | passed, derived | Shape closure and all observation inequalities |
| Empty probes, duplicate times, Gamma=1, tau=0 | passed | Analytic cases and own finite checks |
| Gamma unknown | passed within stated domain | FIFO-only formulas; unknown upper retained |
| Clock/delivery causality and context | passed in inspected implementation | Constructor and route guards; own rejection cases |
| Physical positive homogeneous certificate | passed, derived | Convex ODE solution weights and integral comparison |
| Root existence/bracketing and physical horizon | passed | Exact primitive check and endpoint/exhaustion checks |
| Monotone route composition and regret | passed, derived | Induction/minimum argument under fixed field/coverage |
| Label setting, ties and zero cycles | passed in scope | Proof conditions; 24 own exact graph comparisons |
| Domain exhaustion | passed for evaluated labels | Lower and upper-only exhaustion raise ValueError |
| External actual-domain/field/graph validity | conditional input | Cannot be learned from sparse probes alone |
| Stored 124 passage experiment assertions | passed, exact finite check | Independent closed primitive, rational endpoint checks |
| Universal correctness from enumeration alone | not claimed | Enumeration supplements the analytic proof |
| Native city ETA / 100k/24h validation | out of scope | No native run or native measurements in this review |

## Independent execution and exact experiment checks

Created only R6_independent_fifo_repro.py, its .log/.exit, and this report under
artifacts/v03_origin_validation_20261123.

Actual command, from the review worktree:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 artifacts/v03_origin_validation_20261123/R6_independent_fifo_repro.py

Observed exit: 0. Wrapper wall time: 0.17651592899346724 seconds.
Result: INDEPENDENT_EXACT_CHECKS_PASSED.

The independent script checks:

- 400 input-interval/Gamma/floor cases on a different complete 3-clock integer
  family; 335 feasible cases. Enumeration is directly against the inequalities,
  and envelope endpoint extrema match every feasible finite family.
- Empty/singleton domains, consistent/inconsistent duplicate times, unknown
  uppers, causal/context/measurement-kind rejection, and lower or upper-only
  next-domain exhaustion.
- 24 distinct directed-graph configurations against complete simple-path
  enumeration, including ties, zero-time cycles and several legal alternatives.
- All 124 stored physical roots and their predicted intervals with a separately
  written primitive, not the production distance integrator.
- Raw JSON/log summary equality, exact source hash bindings, and the known
  physical-horizon endpoint root.

For the manufactured velocity, the independent cumulative distance from zero is

    D(t)=2*t+t^2/40                for 0<=t<=20,
    D(t)=4*t-t^2/40-20             for 20<=t<=40,
    D(t)=2*t+20                    for 40<=t<=100.

All stored brackets [a,b] satisfy D(a)-D(entry)<=length<=D(b)-D(entry)
and width<=1e-10 seconds, by exact fractions. The admitted probe counts for
lengths 5,10,20,30 metres are respectively 4,4,3,2 under the stated completion
rounding and one-second delivery rule.

The forcing's one-sided values, together with v(0), give bounds [19/10,31/10];
Gamma=31/19 is therefore a genuine manufactured-field certificate.
For every entry <=60 and length <=30, the invariant lower speed also gives exit
<=60+30/(19/10)<100, so the full declared single-link physical coverage is adequate.

At departure 20, the actual direct and 20+20 detour clocks can independently be
written as 80-40*sqrt(2) and 80-20*sqrt(5) seconds. The stored brackets enclose
these through the respective 10- and 40-metre integral equations.
The detour's final compounded bracket can be wider than an individual root's
1e-10 tolerance; the document only claims that tolerance for each root solve.

The stated direct/detour bounds, positive dominance gap and general regret bound
agree with the raw rational data. The experiment's upper-minimizing direct path
has zero regret among the declared paths by strict dominance.
The general 3.4555878388548993-second bound remains a valid looser certificate.

## Source and author-evidence checks

R2_theory_sources.json correctly distinguishes source context from this paper's
new interval/FIFO statement and does not claim global novelty.
The reported CAS result concerns one oriented triangle case only; it is not
treated as proof of the complete result. Its logged failed tool call is preserved
as ERROR and not counted as validation.

Independently retrieved Dean's author-hosted PDF:
https://people.csail.mit.edu/bdean/tdsp.pdf
Section 2 defines nondecreasing arc arrival maps and composition, Section 3.4
covers cycles/waiting, and Section 4.1 gives the label-setting variant.
These are compatible with the stated reuse.

The publisher's indexed primary page independently confirms Sung, Bell, Seong
and Park (2000), DOI 10.1016/S0377-2217(99)00035-1, its time-dependent speed
model, non-passing property and Dijkstra modification:
https://www.sciencedirect.com/science/article/pii/S0377221799000351
Direct page opening returned HTTP 403; the indexed publisher text was available.

The AMS McShane PDF returned HTTP 403 at both supplied and alternate primary URLs.
The author's prior Exa retrieval was read as provenance, not independently
reproduced here. Exact Theorem 1/page-838 attribution therefore remains an
unreproduced bibliographic check in this pass. It is not a load-bearing gap:
the directed interval extension is fully proved internally above.
No blanket literature novelty or exhaustive literature audit is being asserted.

The author log contains 11 passed in 0.34s. This review did not run that pytest
command. The former 50-versus-34 fixture expectation is consistent with the
present explicit combinatorial count; it is a historical fixture error, not a
counterexample to the current theorem. No original R7 evidence was overwritten.

A focused rg inspection of src found the research classes only in their own
module. No production R02/native call site was introduced by the reviewed module.
No Cargo, full-repository CI, city simulation or performance campaign was run.

## Findings, safe conclusion and stopping boundary

Material findings: **none**. No valid counterexample to the stated claims was
found, and no mathematical or code repair is required for this bounded result.

Strongest safe statement: delivered, population-matched passage intervals and
an independently justified expansion/floor certificate determine sharp FIFO
arrival envelopes in the declared function class. Their legal-path compositions
give conditional fixed-field route and regret guarantees on covered domains.
The exact manufactured physical example and finite checks support the actual
implementation assertions at their specified ranges.

Remaining integration obligations were already explicit: acquire real matched
native boundary observations, justify physical bounds/coverage in any proposed
native regime, and account for rerouting-induced field changes. They do not
invalidate the present restricted theorem and do not authorize another review loop.

Drift watchdog: ALIGNED_WITH_OPEN_OBLIGATION. This advances explainable causal
route observables for the original mesoscopic/finite-response goal. Demand,
native traffic representation, physical contracts, caps and production behavior
were unchanged. The finite mathematical reference is not empirical city evidence.

Skill context used: PhysMath Research Loop 1.3.0 SKILL.md, R6 section of
references/THEORY_LOOP.md, references/POLICY_INTEGRATION.md,
references/SUBAGENT_MODE.md; mathbox proof-audit SKILL.md and its general,
computation and source obligation sections. One independent pass, no descendants,
no review-of-review. Review complete; stop here.
