# MetroFlow: source-aligned rank cursors and conservative FIFO measures

Base read: `606b3ac6a899ba5b8b9ac064d82f609c7ff6cadf`,
`crates/metroflow-rust/src/v1_road.rs`, especially `served_parts` (1528),
`portion` (1541), `interval_packets` (3073), and partial remainder (3924).
This is a constructive research proposal for integration, not a completed V03 run.

## 1. Exact conditional proposition: source-aligned rank cursor

Fix ONE current V1 head packet, whose ordered rows have keys `(tag, offset)`,
positive masses `m_j`, nonnegative origin-birth first moments `b_j`, and original
entry endpoints `(a_j,beta_j)`. Write `M=sum_j m_j>0`. These are the actual
objects consumed by `served_parts` and `portion`. In the present source, every
partial service applies the same fraction to all row masses and birth moments,
and does not change that head's keys or endpoints. The remainder is a newly
materialized vector. This is the bounded target; no claim about arbitrary
network-wide history compression is needed to change this operation.

**Proposition RC (exact real arithmetic).** Let service increments `d_k>=0`
satisfy `Q_k=sum_{l<=k}d_l<=M`. Set `r_0=M` and, for `r_{k-1}>0`,
`f_k=d_k/r_{k-1}`. Repeated original proportional service and remainder satisfy

`m_j^(k) = m_j (1-Q_k/M)`,
`b_j^(k) = b_j (1-Q_k/M)`,
`served_j(k)=m_j d_k/M`,
`served_birth_j(k)=b_j d_k/M`.

The zero-remainder case is terminal; requesting positive further service is an
error. The source may contain zero rows: they contribute zero and may be filtered
with the same explicit source convention.

**Proof.** At step zero the claim holds. If it holds at step `k-1`, its total
remaining mass is `M-Q_(k-1)`. Therefore multiplying every row by
`f_k=d_k/(M-Q_(k-1))` yields exactly `m_j d_k/M`; the same calculation holds for
`b_j`. Subtracting this served fraction gives `m_j(1-Q_k/M)` and the corresponding
birth moment. Induction establishes the identities for any finite subdivision.
Adding served and remainder recovers every source row, so conservation holds
individually by tag, route offset, class, persons/vehicle conversion, and any
fixed additive attached attribute. All coefficients are nonnegative.

**Causal supplement.** If the actual physical eligibility frontier is `E(t)`
in the same absolute mass coordinate, impose `0<=Q(t)<=E(t)<=M`. A service
operation at time `t` permits only `0<=d<=E(t)-Q(t)`. Increasing `Q` cannot serve
a later mass rank before an earlier one. Existing V1 packets can initially use
their already-computed `ready` time: `E(t)=0` before readiness and `M` thereafter.
This retains the source's finite-response motion law. A continuous within-packet
eligibility curve is a separate physically more resolved model, not silently
equivalent to this source adapter.

**Physical interpretation.** This is a conservation and causality statement for
a homogeneous conditional mixture, not a vehicle-level assumption. The labels
and birth moments remain distinct. Rank is service amount, not origin birth
time, and not an invented chronological order between simultaneously mixed
commodities. In particular, do not replace the original remainder endpoints by
`a+(beta-a)Q/M`: the present source preserves its `(a,beta)` values on remainder.
Outgoing events still receive the exact service interval from the physical clock.

**Computational form.** Store one immutable ordered source composition plus a
span `[lo,hi]` in its mass coordinate. The remaining state is only that span and
the original packet metadata; `take(d)` returns `[lo,lo+d]` and `[lo+d,hi]`.
Rows are evaluated as root row times `(hi-lo)/M`. A root can be shared by both
immutable old and new snapshots. Service never allocates another row vector.
For `N` source rows and `K` live spans the payload is `O(N+K)` instead of `O(NK)`;
iterating all rows remains `O(N)`. This does not prove that the whole network
has bounded complexity: interval overlay, source mixing, events and discarded
roots need their own ownership rules. It removes one identified materialization.

## 2. Concrete adapter contract for the existing road engine

Suggested additive internal API, not a new city engine:

```
CompositionRoot { ordered_keys, masses, birth_moments, total_mass }
RankSpan { root: Arc<CompositionRoot>, lo, hi, original_a, original_b }
take(span, amount, eligible_rank) -> (served_span, remainder_span)
iter_rows(span) -> same ordered Part keys and scaled mass/birth payloads
write_legacy_rows(span) -> expanded original wire shape
```

For existing `PacketParts` a source-faithful first implementation can preserve
the root's own `Uniform`, `SharedKeys` or `Mixed` carrier instead of introducing
another key authority. Attach only the service transformation. Restriction to a
physical event interval, route offset advancement and time rewrite remain
explicit separate operations. `take` must check finite inputs and positivity,
reject service beyond eligible rank, and preserve the original metadata.

There are two distinct arithmetic contracts:

1. **Operation-chain view:** an immutable root plus the original sequence of
   scale operations evaluates each row in exactly the original IEEE order.
   It avoids immediate remainder allocation and can preserve binary row values,
   but evaluation cost grows with chain depth. The existing test-only
   `v1_lineage_shadow.rs` already demonstrates this idea; integrate a bounded
   source adapter rather than claiming it as new mathematics.
2. **Collapsed rank cursor:** the proposition above applies exactly over reals
   and rationals. A single floating-point scale generally differs from repeated
   binary64 products; `0.1*0.3*0.7 != 0.1*(0.3*0.7)` is already a source test.
   This mode needs measured numerical equivalence under the current tolerance,
   a new representation/version identity, and a direct old/new physical check.
   Do not call it byte-exact. Compensated rank updates help but do not constitute
   that proof by themselves.

Recommended first falsifier: capture one actual multi-tag original head before
partial service and its real service fractions, replay all fractions eagerly
and through the proposed carrier, compare tag/class/route and birth moments,
nonnegative remainder, exact eligibility and source endpoints. Then run the
actual original 25700->25710 checkpoint path. A synthetic split experiment is
enabling evidence only, not replacement original-city acceptance.

## 3. New controlled-closure proposition: sharp mass-rank error certificate

An optional model revision can go beyond the exact existing head. Let a queued
mass interval of length `h` carry an arbitrary measurable commodity fraction
`rho(s)` with `0<=rho<=1`, `s in [0,h]`. Its cumulative commodity mass is
`F(x)=integral_0^x rho(s) ds`, total `m=F(h)=p h`, `p in [0,1]`. Preserve `h`
and `m` exactly but represent the intra-block mixture by the constant `p`.
This defines `Fbar(x)=p x`.

**Proposition RB.** For every prefix `0<=x<=h`,

`max(0,m-(h-x)) <= F(x) <= min(m,x)`,
`abs(F(x)-p*x) <= h*p*(1-p) <= h/4`.

The constant `1/4` is sharp. It is attained by a block whose first half is pure
commodity A and second half pure B, at the middle prefix. The averaging closure
therefore preserves total mass and each commodity's whole-block total exactly,
while its order error is explicitly controlled in mass units.

**Proof.** Positivity bounds `F(x)` below by zero; the tail can carry at most
`h-x`, giving the other lower bound. It is bounded above both by its whole-block
mass `m` and the prefix's total mass `x`. Subtract `px`. The upper deviation is
`min(ph,x)-px`: it rises with `x` until `x=ph` and falls thereafter, attaining
`hp(1-p)`. The lower deviation is `px-max(0,ph-h+x)`: it attains the same maximum
at `x=h(1-p)`. Finally `p(1-p)<=1/4`.

For a vector of nonnegative commodity fractions summing to one, apply this
argument to any union of labels. The supremum of signed prefix error over
label subsets is at most `h/4`; equivalently half the L1 discrepancy of the
zero-sum commodity-prefix vector is at most `h/4`. This controls total variation
of the *finite submeasure* at a fixed prefix, not normalized probability TV
after division by a possibly tiny served mass.

Partition a queue into fixed rank blocks with mass at most `delta`, retaining
the exact total of each label in each block. Complete preceding blocks cancel,
so EVERY cumulative service-prefix error is at most `delta/4`, independently
of the number of partial-service calls. An arbitrary served interval has two
boundary cuts, hence error at most `delta/2`. Repeatedly re-averaging remainders
does not have this guarantee; the immutable rank partition is essential.

For an additive attribute `z(s) in [zmin,zmax]`, retaining its whole-block first
moment gives prefix error at most `h*(zmax-zmin)/4`. For source birth time this
has units vehicle-seconds. Keep birth order separate from FIFO priority; birth
need not be monotone. Unknown attribute bounds yield no claimed certificate.

**What this removes.** Bound the number of blocks by approximately `M/delta`
and retain a cursor rather than a new row history after every service split.
The approximation scale is physical mass, not arbitrary elapsed-time bins.
The theorem supplies an a priori accuracy knob and an actual falsifier,
instead of assuming history can be merged losslessly.

**Scope restriction that matters for MetroFlow.** This is a bound for a fixed
input measure and specified cumulative service. It does not bound an entire
coupled city trajectory. Head composition enters `rates`, receiving space,
class-dependent closure and subsequent routing; near zero supply a tiny rare
blocked component can change a service decision. A small cumulative error does
not bound an instantaneous derivative or establish Lipschitz stability of this
hybrid network. Keep exact blocks at routing/supply discontinuities or measure
the resulting operator and observable error directly. Do not use `delta/4` to
waive the current conservation tolerance or certify 24-hour V03.

## 4. Finite-response eligibility in a cumulative formulation

For a separate continuous common-speed link, assume an initially empty link
and a specified inflow history `A(0)=0`. Let `v(t)>=0` be locally
integrable and `X(t)=integral_0^t v(u)du`. A mass element entering at `tau(q)`
is physically eligible after travelling length `L>0` precisely when
`X(t)-X(tau(q))>=L`. If `tau(q)` is nondecreasing, eligible ranks form a prefix.
Thus `E(t)=sup{q<=A(t): X(t)-X(tau(q))>=L}` and `D(t)<=E(t)<=A(t)` preserve
causality and FIFO while allowing finite acceleration, stops and delayed
response through the original speed law. Occupancy is `A-D`; per-label
occupancy is `C_j(A)-C_j(D)`. This transports source composition by rank,
instead of replacing finite-response motion by instantaneous LWR speed.

Proof: `X` and `tau` are nondecreasing, so the eligibility predicate is
downward closed in q; integration of its indicator gives E. Restriction by
an increasing departure frontier D preserves order. Commodity conservation
follows by subtracting the same cumulative functions at identical frontiers.
Nonempty initial stock requires an initial distance/eligibility profile as an
additional input; inferring it from total stock alone is invalid. This is
conditional on common link speed and monotone entry rank; it is not a
claim that arbitrary class-specific overtaking trajectories have one frontier.

## 5. Actual checks and primary-source relationship

`rank_fifo_proposal_checks.py` verifies exact rational source identities for
120 independently generated heads of 1,2,7,31 rows and 25 service subdivisions
each; all ordered row masses and birth moments are compared to the repeated
source operation. It rejects service beyond a stopped eligibility frontier.
It also exhaustively verifies RB at every integer cut of every binary label
sequence of length 1 through 10. These finite checks do not replace the proofs.

Wolfram Language checked the three identities for two consecutive services:
remainder mass, cumulative served mass, remainder birth moment; output
`{0,0,0}` under `M>q1+q2`, `q1,q2>=0`. Wolfram also returned `True` for both
prefix envelopes and `hp(1-p)<=h/4` and found the exact maximum `hp(1-p)`.

Relevant primary sources retrieved with Exa/Parallel (2026-11-23):

- Yperman et al., *The Multi-Commodity Link Transmission Model for Dynamic
  Network Loading*: cumulative vehicle counts disaggregated by route and
  boundary inverse-time composition are established traffic-model tools.
  https://www.mech.kuleuven.be/cib/verkeer/dwn/pub/P2006A.pdf
- W.-L. Jin, *Continuous formulations and analytical properties of the link
  transmission model*, arXiv:1405.7080: commodity outflow composition is pulled
  from upstream composition at the entry time associated to the same cumulative
  vehicle count; retrieved Eq.31b--d (another rendering uses Eq.43b--d).
  Its derivation assumes first-order LWR with a triangular fundamental diagram;
  MetroFlow's finite-response speed law is not supplied by that paper.
  https://arxiv.org/abs/1405.7080
- Bar-Gera and Carey (2017), *Representation requirements for perfect
  first-in-first-out verification in continuous flow dynamic models*, DOI
  10.1016/j.trb.2017.02.002, distinguishes perfect network FIFO and solution
  representations. Their 2022 construction is computationally intensive.
  These sources prevent calling coarse cumulative interpolation exact network
  FIFO. https://doi.org/10.1016/j.trb.2022.04.002

The RC/RB arguments are direct derivations here. No world-first claim is made;
the rank-block error certificate's usefulness is the explicit source/model
boundary and constructive implementation contract. SciSpace searches supplied
secondary indexing of Jin/Jayakrishnan's FIFO-violation work; no unverified
abstract is used as a theorem dependency.

Skill context used: physmath-research-loop 1.3.0 cloud SKILL.md,
references/THEORY_LOOP.md (R4/R5) and POLICY_INTEGRATION.md; mathbox proof-audit
read for quantified boundaries, with checks here labelled author self-check.
Executor alias reads e30/e23/e9/e10 were unavailable in child; cloud plugin
locators worked for physmath/mathbox. No canonical files or branches mutated.
