# MetroFlow: two exact transport reconstructions beyond row packing

**Scope:** R2, R4, R5 contribution to the parent THEORY ONLY R1–R10 run; exploratory alternatives, no production selection. Date: 2026-11-23. Author verification: one source/derivation pass and the small rational calculation recorded in `metroflow_exact_routes_calculation.json`. No repository mutation, native build, production simulation, or push was performed.

## 0. Result and evidence status

Two different reductions are available at the level of mathematics.

1. **A — retain all labels, factor the operators.** An immutable composition expression and a persistent interval-active tree represent the two Cartesian products, head composition × service subdivision and active composition × endpoint slab, without materializing either product. Destination projection, route advancement, marks, receiving queries, and sink reporting have closed operator formulas. The exactness theorem is constructive. Cheap queries and small reachable expression support are additional, measurable requirements; there is no proved global low-rank bound.
2. **B — quotient the physical dynamics, retain lossless fibers.** Equal class and equal complete residual route define a sufficient behavioral equivalence for the currently read road law, provided ordered packet/eligibility boundaries are retained. Physical control evolves on class/suffix amounts. A conditional label measure carries tag, purpose, birth, person, cargo, and service provenance, and is queried when those quantities become active. This is an exact road subsystem quotient with lossless disintegration, not a claim that tag-blind city dynamics are autonomous.

The two constructions can be combined, but have different purposes: A factors repeated linear operations even when no two labels are behaviorally equivalent; B reduces the number of independent physical control channels when such equivalence actually occurs. Neither result asserts that the original 100k, 24-hour run fits its resource budget. Their next remaining cost is stated explicitly below.

**New useful obstruction, with constructive repair:** even equal adjacent mixture densities cannot generally have their *head/service boundaries* erased under the source midpoint mark rule. A concrete finite-response counterexample is proved in §4. Retaining virtual boundaries repairs this while allowing all composition storage to be shared.

Status ledger:

| Claim | Status | Evidence |
|---|---|---|
| Algebraic closure of A under the listed consumers | derived | §§2–3 proofs |
| Persistent overlay representation avoids label × slab allocation | derived, conditional complexity | §2.4 construction |
| B class/suffix quotient commutes with the read road transition | derived for exact-real counterpart | §5 induction |
| Tags can be discarded permanently | refuted | service thresholds and route-tail counterexamples |
| Equal mixture slabs may always be coalesced | refuted | §4 finite-response mark calculation |
| Worked examples | exact-rational checked | companion JSON; Python `Fraction`, exit 0 |
| Full IEEE agreement; native integration; resource sufficiency | not run / unresolved | no such claim is made |
| Global compact support or uniform low rank | unresolved | no constructive global bound supplied |

## 1. Source identity and field-to-model map

Read remote repository `/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123` on device `edd1b263-56a0-4391-8a2a-677dd00eabf5`. `git rev-parse HEAD` returned `492e27618696df2514b088a64de450cf69746647`. A later `git diff --quiet HEAD --` over the four files below completed and `rev-parse` returned the same SHA, binding the working-tree reads to this head.

| Source | Git blob |
|---|---|
| `AGENTS.md` | `49d9467f7bf6394b5adb09d8ecc774c7a0da0d9d` |
| `crates/metroflow-rust/src/v1_road.rs` | `f2d2031e8710b57b6b1be430ece7695430c19eb3` |
| `crates/metroflow-rust/src/v1_journey.rs` | `34a0e1fc2841a1dba29684c77e1c0e15aa69c5df` |
| `docs/research/V03_CAUSAL_FIFO_THEOREMS_20261123.md` | `869143757bc46417290d277e2d0c396807ef001e` |

Also read `src/metroflow/v1/native_road.py`, especially class construction and snapshot conversion. No independent blob digest was requested for that auxiliary field-name map.

The prior theorem document already proves proportional scaling of one fixed homogeneous head and a local rank-block error bound. Those results are reused, not presented here as new. The new construction connects composition roots to interval overlay, route transforms, physical queries, mark contractions, service/journey sinks, and retained observer history.

| Actual field / operation | Mathematical object, units | Necessary retained structure |
|---|---|---|
| `Part.tag` | immutable registry label \(\ell\) | route identity, vehicle class, external service/journey identity; purpose need not alter road motion but remains recoverable |
| `Part.offset` | position \(o\) in the registered route | complete remaining route; projection alone is insufficient |
| `Part.mass` | \(m_z\ge0\), vehicles, \(z=(\ell,o)\) | continuous mesoscopic amount |
| `Part.birth` | \(B_z\), vehicle·s | first origin-birth moment, **not** a timestamp; \(B_z/m_z\) is mean birth time when mass is positive |
| `Part.a,b` | entry interval endpoints, s | uniform interval measure, or point atom when equal; missing values remain a distinct legacy state until producers assign finite endpoints |
| `Packet.target` | target of cell progress, m | readiness depends on target and cell motion; cannot be inferred from total mass |
| ordered `Cell.packets` | ordered queue of composition slabs | all original head/point/slab cuts and tie ordering are retained as virtual metadata |
| `Cell.v` | progress, activity, admitted/completed amount, entry/exit moments, vehicle-metres, speed | physical state remains explicit; snapshot order verified in `native_road.py:60–68` |
| `Cell.latent[class]` | dimensionless latent state | class identities and values retained |
| `class()` / `path()` / `dest()` | \(c(z),p_\ell,o\mapsto p_\ell[o+1]\) | `v1_road.rs:3030–3045` |
| `footprint()` | \(L_z\), m/vehicle | class length plus standing gap, class array index 12 |
| `served_parts`, `portion` | common scalar multiplication of both mass and birth | `v1_road.rs:1626–1653`; exact-real factoring changes rounding order |
| `beta`, `beta_space` | destination mass and occupied-length fractions | `v1_road.rs:3693–3717` |
| `rates` | weighted progressive allocation with active constraints | `v1_road.rs:3324–3381`; preserve saturation and source priority rules |
| `interval_packets` / `combine_interval_mapped` | restriction of a vector measure to endpoint slabs | `v1_road.rs:3171–3323,2295–2346` |
| incoming `Mark` | source speed and class latent sampled at event midpoint | `v1_road.rs:3980–4010,4196–4253`; contracts with mass before interval combination |
| `EventRow` | tag, source cell, destination, amount, start, end, birth | retained detailed observer carrier; distinct from the sink marginal |
| `service.finish` | tagwise sink sums, then bus/freight nonlinear updates | `v1_journey.rs:794–851` |
| `journey.finish` | tag-dependent egress delay pushforward, receipt completion | `v1_journey.rs:2015–2180` |

Class physics in `native_road.py:28–32` includes preferred speed, response time, acceleration/braking, minimum gap, headway, vehicle length, latent/restart/hazard parameters, gap scale, entry speed, and standing footprint. `motion` first computes class amounts, occupied length and common gap; then class latent relaxation and a common finite-response characteristic (`v1_road.rs:3082–3169`). Keep its two length conventions distinct: the motion gap uses class vehicle length (index 6), \(g=(\mathrm{spacecap}-\sum_kn_k\ell_k)/\sum_kn_k\); storage/receiving space uses the standing footprint (index 12). Both are exact class contractions. None requires materializing a row for every service subdivision once its relevant contractions are available.

### Arithmetic contract

The proofs below use exact real arithmetic for the **existing time-discrete source algorithm**, including its homogeneous-head interpretation, target-based readiness, midpoint marks, given tick boundaries, and deterministic branch conventions. Source threshold constants such as fraction snapping may be retained as explicit rules. An exact real calculation is not a statement that binary64 follows the same branch after regrouping. Underflow deletion, signed zeros, operation order, compensated-clock bit patterns, resource guards, and serialization bytes need a separately declared compatibility contract.

In particular, the nonlinear coupled source timestep is not asserted to be a time-subdivision-invariant semigroup. Only the conditional linear transport operators have the algebraic composition law used below.

## 2. Route A: composition expressions and interval measures

### 2.1 Objects and primitive operators

Let \(Z\) be the finite registry of legal `(tag,offset)` pairs, with \(|Z|=L\). A composition is the pair of finite positive measures

\[
v=(m,B),\qquad m=\sum_{z\in Z}m_z\delta_z,
\quad B=\sum_{z\in Z}B_z\delta_z.
\]

Here \(m_z=0\Rightarrow B_z=0\); every checkpoint's represented birth information is retained. No unrepresented individual birth distribution is invented. Immutable basis roots contain only composition payloads and static registry references. They do not own a `RoadState`, a `Cell`, an old queue, or a closure capturing one.

The expression language has the following nodes:

\[
\operatorname{Scale}_a(v)=av,\quad
\operatorname{Sum}(v,w)=v+w,\quad
P_jv=1_{\operatorname{dest}(z)=j}v,\quad
Rv=(z\mapsto(\ell,o+1))_\#v.
\]

The symbol \(j=\partial\) denotes the sink; \(R\) is used only on nonterminal labels. A class-dependent mark or additive observable uses a diagonal multiplier \(D_gv=g(c(z))v\), with its units carried by the output channel. All inputs to transport stay nonnegative; signed expressions are unnecessary for implementation.

For a service interval \(I=[a,b]\), define the probability measure

\[
U_I(dt)=\frac{1_I(t)}{b-a}\,dt\quad(a<b),
\qquad U_{[a,a]}=\delta_a.
\]

An incoming ribbon is \(v\otimes U_I\). A destination's entire incoming measure is

\[
\mathcal F_j=\sum_{e\to j} RP_j(f_e v_e)\otimes U_{I_e}.
\tag{A1}
\]

Store each summand as a small operator/interval descriptor referring to its existing root; no tag rows are copied. The service remainder is \((1-f_e)v_e\) with its original entry endpoints and target. A service interval overwrites outgoing entry endpoints, as in the source; it does not cut the remainder's old interval at an invented entry time.

### 2.2 Closure and commutation lemma

**Lemma A1.** For any finite expression built from positive roots by Scale, Sum, destination projection, route advancement and class weighting, restriction of the associated interval measure to a finite union of intervals and point sets, and any finite additive query, are well defined without expanding the label support. The expression language is closed under these operations, using the resulting finite interval/atom descriptors. In particular,

\[
P_j(av+bw)=aP_jv+bP_jw,
\quad R(av+bw)=aRv+bRw,
\]

\[
\langle\phi,Rv\rangle=\langle\phi\circ R,v\rangle,
\quad \langle\phi,P_jv\rangle
=\langle1_{\operatorname{dest}=j}\phi,v\rangle,
\tag{A2}
\]

and, for any elementary slab \(J=[s,t]\) in the union of ribbon endpoints,

\[
\mathcal F_j(J)
=\sum_{e:\,J\subseteq I_e}
\frac{t-s}{|I_e|}\,RP_j(f_ev_e),
\tag{A3}
\]

with point atoms processed separately in the original point-before-slab order.

**Proof.** Scalar multiplication, addition and deterministic pushforward act componentwise on both positive measures. Projection is multiplication by an indicator. Thus linearity and the pullback identities follow directly by finite summation. Restriction acts only on the time factor, so it commutes with the label operators. On an elementary slab each interval indicator is constant in the interior, hence integration gives (A3). The source `combine_interval_mapped` computes exactly \(m_z|J|/|I_e|\) and \(B_z|J|/|I_e|\), then sums equal keys. Those are precisely the coordinates of (A3) in real arithmetic. Endpoints have zero Lebesgue mass; positive point masses use the separate atom formula. ∎

This proves closure through **the interval consumer**, not merely through head scaling. `combine` is addition of measures on common labels and common endpoint metadata. Canonical key sorting can be deferred to a requested legacy view.

### 2.3 Physical query lemma and feedback

For a current head \(v\), required quantities are contractions:

\[
M=\langle1,m\rangle,
\quad M_k=\langle1_{c=k},m\rangle,
\quad M_j=\langle1_{\mathrm{dest}=j},m\rangle,
\]

\[
\beta_j=M_j/M,
\qquad \beta^{\mathrm{space}}_j
=\langle L_z1_{\mathrm{dest}=j},m\rangle/M.
\tag{A4}
\]

Cell occupancy, length occupancy, class support, birth totals, and class ledger increments have the same form. The finite-response function receives exactly its original class totals and latent state. Its nonlinearity causes no closure defect: the same inputs give the same characteristic, readiness and marks. The junction allocation receives exactly (A4), the old sending/receiving values, and priorities. It therefore has the same exact-real event increments, including genuine active-constraint changes.

For service event \(e\) from cell \(i\), with absolute midpoint \(\bar t_e\) and source tick beginning \(t_n\), let \(v_i(u),p_{i,k}(u)\) denote the source motion/latent functions at local time \(u\). The incoming speed numerator to destination \(j\) is

\[
\sum_e v_i(\bar t_e-t_n)\,\langle1,P_j(f_em_e)\rangle.
\tag{A5}
\]

The class-\(k\) latent numerator is

\[
\sum_e p_{i,k}(\bar t_e-t_n)
\langle1_{c=k},P_j(f_em_e)\rangle.
\tag{A6}
\]

These are exactly the source mass–mark contractions before interval combination. There is no need to retain one duplicate Mark per tag. Survivors are added with their original latent values and normalization. Waiting and transfer hold use the same contractions multiplied by the original event durations. Repeated nonnegative decrements with a zero clamp satisfy
\(\max(0,\max(0,x-a)-b)=\max(0,x-a-b)\), so aggregate receiving updates also agree over reals.

**Theorem A2, conditional source equivalence.** Start from a source state, keep its ordered packet cuts/targets, and use exact contractions for all controls, marks and ledgers. Replace each eager service/overlay construction by (A1)–(A6). Then after any finite sequence of the source tick/event operations, expanding the expressions gives the same exact-real mass and birth coordinates, target/entry metadata, physical cell state, and detailed event measure as the eager algorithm.

**Proof.** A common initial state gives the same `motion`, readiness and head ordering. Equations (A4) give the same rates and same next minimum event duration. Scale gives the same served and remainder coordinates. Projection and route pushforward give the same destination coordinates. Equations (A5)–(A6) give the same new speed/latent values. Lemma A1 supplies the same next ordered interval packets. This closes one event/tick; induction proves the finite sequence. Branches on zero support must be evaluated exactly, and virtual cuts are part of the induction state. ∎

The theorem does not freeze the service trace externally. It specifies the contractions necessary to recompute the same feedback trace. Its numerical implementation remains open.

### 2.4 Constructive representation and complexity

For \(E\) incoming ribbons in a destination/tick, assign each ribbon a leaf in a balanced persistent active tree. The leaf is zero before its start and after its end; while active it holds its density expression \(v_e/|I_e|\). Interior nodes are Sum nodes. A start/end update copies only the \(O(\log(E+1))\) path. Every elementary slab stores a pointer to the current tree root and its width, rather than the sum's expanded tag vector. Point atoms have analogous small lists/roots.

This uses positive leaves and deletion-to-zero, avoiding the cancellation that a numeric signed endpoint-difference accumulator would introduce. The signed identity \(dH=\sum_e(v_e/|I_e|)(\delta_{a_e}-\delta_{b_e})\) is a mathematical description, not a recommendation to subtract nearly equal floating-point vectors.

Let:

- \(N\): immutable source support rows actually retained, including newly released cohorts;
- \(S\): nonzero head-service operations retained in the expression ancestry;
- \(D\): nonempty destination branches of these operations;
- \(E\): ribbon insertions across the overlay calls, and \(K\): distinct scalar endpoint/point knots; \(K\le2E\) per call for finite intervals, but distinct interval pairs are **not** endpoint counts;
- \(V\): reachable expression nodes over all currently live roots;
- \(Q_*\): distinct `(expression node, pulled-back query)` pairs actually evaluated/cached;
- \(Z_{\mathrm{out}}\): detailed coordinates explicitly requested at export/report boundaries.

The constructive overlay cost is \(O(E\log(E+1))\) descriptor storage/time plus its query work; storing slab headers costs \(O(K)\). Each service/destination transform adds \(O(1)\) nodes, so a sufficient ancestry bound has the form

\[
V=O\!\left(N+S+D+\sum_{\rm overlay}E\log(E+1)+K\right),
\tag{A7}
\]

when nodes are not needlessly rebuilt and old unreachable nodes are collected. The root support itself may grow without bound over simulation time; (A7) is a count of actual source/control history, not a constant city-size bound.

Memoized scalar contractions can evaluate a query using (A2). If a finite required query family \(\mathcal W\) is closed under operator pullbacks, and its leaf values are indexed, each unique node/query pair is evaluated once. Work is proportional to \(Q_*\) plus indexed leaf work and explicit output. Cached class/destination/path-suffix queries provide one implementation strategy. A basis for a \(q\)-dimensional invariant query space gives finite summary updates, with costs determined by the actual operator matrices' sparsity.

**Compatibility limit:** that invariant query family need not be small. Arbitrary per-tag future controls may require the full label coordinate space. Distinct routed ancestry can also generate many pulled-back masks. Without an index/closure bound, cheap storage may move the bottleneck into repeated expression traversal. There is no deduction here that \(Q_*\ll NS\), or that every large composition has low rank. A rule that retains roots without any query plan is incomplete.

### 2.5 Lifetime rule

Count the union of nodes reachable from the actual input/current/candidate state roots, retained event-query roots, and pending journey/service roots. Count each queue/slab descriptor owner separately. A root owns only immutable composition data, scalar transforms and child composition pointers; it must not retain the entire state in which it arose. Unreachable nodes and query caches can be released. Old snapshots keep precisely their reachable dependencies alive.

An expression DAG may still retain a long ancestry when live packets depend on it. Collapsing consecutive scalar factors over reals and deleting zero branches is justified; collapsing arbitrary route filters or erasing required event knots is not. The next resource question is the measured reachable support \((N,V,Q_*)\), including all immutable snapshots, rather than merely the count of new headers.

## 3. Route A worked calculation and downstream closure

Take two roots over three labels, with entry times later than their birth times:

\[
U_m=(4,2,0),\ U_B=(8,10,0),
\quad V_m=(0,2,2),\ V_B=(0,12,16).
\]

Two services emit \(U/2\) on \([10,12]\) and \(U/2\) on \([12,14]\); another source emits \(V\) on \([11,13]\). The former head is shared across its services. Overlay gives:

| Slab | Mass vector | Birth vector |
|---|---|---|
| [10,11] | \((1,1/2,0)\) | \((2,5/2,0)\) |
| [11,12] | \((1,3/2,1)\) | \((2,17/2,8)\) |
| [12,13] | \((1,3/2,1)\) | \((2,17/2,8)\) |
| [13,14] | \((1,1/2,0)\) | \((2,5/2,0)\) |

Their totals are \((4,4,2)\) and \((8,22,16)\), exactly \(U+V\). The middle two slabs can share a density expression while keeping their boundary at 12.

For the second slab let labels 1,3 continue to J, label 2 to K, and footprints be \((1,2,1)\) m/vehicle. Then

\[
M=7/2,
\quad(\beta_J,\beta_K)=(4/7,3/7),
\quad(\beta_J^{\rm space},\beta_K^{\rm space})=(4/7,6/7).
\]

For a single incoming head with sending rate 4 vehicles/s and receiving rates \((2,1)\), progressive allocation reduces to

\[
q=\min(4,2/(4/7),1/(3/7))=7/3\ \mathrm{vehicles/s}.
\]

A permitted event of duration \(h=3/7\) s serves one vehicle, fraction \(f=2/7\):

\[
m_{\rm served}=(2/7,3/7,2/7),
\qquad B_{\rm served}=(4/7,17/7,16/7).
\]

J receives \(4/7\) vehicle and \(4/7\) m; K receives \(3/7\) vehicle and \(6/7\) m. Projection followed by route advancement operates on the same root. If service starts at 20 s, its midpoint is \(283/14\) s; served mass–age is \(283/14-37/7=209/14\) vehicle·s. All fractions and totals were checked exactly in the companion JSON.

### Sink, service, journey, and reporting operators

Define the detailed event measure by attaching tag/source/destination/start/end metadata to each served expression. The current joint loop (`v1_journey.rs:1613–1621`) only sends the sink marginal

\[
\Sigma_\ell=\sum_{e:\,\mathrm{dest}=\partial}
(f_em_e)_\ell\,\delta_{t_e^{\rm end}}
\tag{A8}
\]

to service/journey. `service.finish` forms its per-tag mass sums, then applies bus completion thresholds and freight updates. These nonlinear operations must receive exact tagwise sums; they cannot operate on an undifferentiated sink total.

For a car leg's egress delay law \(H_\ell=\sum_d w_{\ell d}\delta_d\), `journey.finish` constructs the arrival measure

\[
\Gamma_\ell=\Sigma_\ell*H_\ell
=\sum_{e,d}(f_em_e)_\ell w_{\ell d}
\delta_{t_e^{\rm end}+d}.
\tag{A9}
\]

Retiring due stages is restriction to a time prefix, followed by the source's completion-time sampling convention. Thus an expression-valued time measure is closed under delay pushforward, prefix retirement and additive receipt queries. Bus/freight logic keeps its existing explicit state; it supplies the corresponding exact arrival increments.

Person/cargo/purpose summaries are contractions against retained label attributes or against the existing service conversion state; no fixed persons-per-vehicle factor is assumed for a bus whose passenger state changes. Completed histories, age moments and travel cost reports remain available. If a downstream observer insists on every original event tuple or receipt row, expansion costs \(\Omega(Z_{\mathrm{out}})\). Keeping that legacy demand for every internal boundary simply moves the bottleneck to the observer/checkpoint boundary. A new persistent serialization can encode roots and operators with versioned identity; proving its round trip is implementation work, not accomplished here.

This packet directly inspected road/service/journey read sites. Other accessibility/development consumers can remain scientifically unchanged if given these same represented histories/observables; their minimal query surface and efficient adaptation require the parent's source map. Lossless expansion is always the compatibility fallback, not an efficiency guarantee.

## 4. Why equal adjacent densities still need virtual knots

Choose one source cell with the valid unsaturated finite-response law

\[
\dot v=(v_*-v)/\tau,\quad v(0)=0,
\quad v_*=1\ \mathrm{m/s},\quad\tau=1\ \mathrm{s},
\]

and acceleration limit at least \(1\ \mathrm{m/s^2}\), so \(v(t)=1-e^{-t}\) in these units. Consider two adjacent one-second service events, each of one vehicle, with the same labels and density. Source midpoint marking contributes

\[
W_{\rm split}=v(1/2)+v(3/2)
=2-e^{-1/2}-e^{-3/2}.
\]

Removing the boundary and making one two-vehicle event gives

\[
W_{\rm merged}=2v(1)=2-2e^{-1}.
\]

The exact difference is

\[
W_{\rm merged}-W_{\rm split}
=2e^{-1}\bigl(\cosh(1/2)-1\bigr)>0,
\]

approximately \(0.09390194\) vehicle·m/s. With an empty receiving cell this changes the initialized receiving speed by half that value. The same issue can affect latent midpoint marks. All parameters can be chosen inside the unsaturated branch of `characteristic`.

This refutes a specific proposed simplification, not exact symbolic transport. Retain the virtual event/head knot and share the composition expression. Alternatively, replacing midpoint samples by exact time integrals is a scientifically motivated but separately versioned model change; it is not exact equivalence to the present source timestep.

## 5. Route B: behavioral quotient with lossless provenance fibers

### 5.1 Equivalence and disintegration

Fix the currently registered routes and the present road law. Let

\[
\kappa(\ell,o)=\bigl(c(\ell),\ p_\ell[o:]\bigr).
\tag{B1}
\]

This is a sufficient equivalence, not a claim of coarsest possible minimization. Class identity is retained, not merely a coincident current numerical speed, because latent state, support-dependent minima and class ledgers use it. Complete residual route is retained, not only the immediate destination.

Within each **existing ordered packet/slab**, define

\[
M_g=\sum_{\kappa(z)=g}m_z,
\quad \bar B_g=\sum_{\kappa(z)=g}B_z,
\quad K_g(z)=m_z/M_g\quad(M_g>0).
\tag{B2}
\]

Retain also the conditional birth first-moment measure
\(J_g(z)=B_z/M_g\). Then

\[
m_z=M_gK_g(z),\qquad B_z=M_gJ_g(z).
\tag{B3}
\]

\(K_g\) is a probability measure on the label fiber; \(J_g\) has seconds as units and need not be proportional to \(K_g\) by a single scalar. Formula (B3) is a lossless disintegration of all source-represented mass and birth information. Purpose, original origin/destination, person/cargo attributes, service tags and finite-information state remain attached to labels or existing external state.

The physical queue stores the \(M_g\), original cut/target metadata, and cell physical state. The fibers can be immutable shared measures or a cumulative provenance representation. They are not copied eagerly at every physical split. A homogeneous service fraction changes only \(M_g\), leaving \(K_g,J_g\) unchanged.

### 5.2 Hybrid quotient theorem

Let \(Q\) map every packet's label measure to its class/residual-route amounts while preserving all queue boundaries, target metadata, class latent state, physical cell variables and necessary physical ledgers. External offered physical compositions are mapped by the same \(Q\).

**Theorem B1.** For the read exact-real road transition \(T\), under the fixed registry and identical input/tick/control calendars,

\[
QT=\bar TQ,
\tag{B4}
\]

for a deterministic quotient road transition \(\bar T\). Moreover, transporting fibers using (B3), the following scale, projection, route-advance and mixture rules reconstructs the complete eager label state and event measure.

**Proof.** Class totals are sums of the \(M_g\); therefore cell gap, class support, response/latent coefficients and common characteristic are functions of \(Qx\). Targets and queue order are retained, so readiness agrees. Immediate destination and footprint are constant on each group, making the head fractions and occupied-space fractions functions of group amounts. Consequently sending, receiving, progressive allocation, event duration and fraction snapping agree. Common service scales commute with \(Q\). Destination projection selects entire groups. Route advancement maps a group to the class and tail of its residual route, so it has a deterministic quotient map. Mark functions depend only on source cell, class and midpoint; their contractions are groupwise sums. Overlay and equal-key addition commute with \(Q\) by linearity, while the original knots remain present. This proves (B4) for one tick and hence finite iteration. The fiber formulas reconstruct every label term at each of these operations, proving the stronger lossless statement. ∎

If several incoming pieces become the same quotient group with masses \(a_r\) and fibers \((K_r,J_r)\), the exact mixture update is

\[
M'=\sum_ra_r,\qquad
K'=\frac{\sum_ra_rK_r}{M'},\qquad
J'=\frac{\sum_ra_rJ_r}{M'}.
\tag{B5}
\]

When source entry intervals differ, first restrict each piece by its exact overlap coefficient, then apply (B5) separately on each retained slab. Hence service, route advance and interval overlap all remain closed. Empty groups are omitted and no division by zero is performed.

The full *coupled city* is not determined by quotient road amounts alone: bus/run completion, individual journey laws, route replanning and demand feedback may inspect fiber labels. The augmented state retains their original explicit states and supplies exact tagwise contractions, such as (A8)–(A9), at each such interface. This yields the original coupled transition if those interfaces are adapted or exactly expanded. Calling the quotient itself an autonomous city model would be false.

### 5.3 Nontrivial example

In one current head, labels \(a_1,a_2\) have class C and identical residual route \([i,j,z]\); labels \(b_1,b_2\) have class D and identical residual route \([i,k,z]\). Their masses and birth moments are

\[
m=(3,1,2,2),\qquad B=(6,4,2,10).
\]

The two physical groups both have mass 4. Let footprints be 1 for C and 2 for D. With sending rate 3 and receiving rates \(R_j=3/2,R_k=1/2\), both turn fractions are \(1/2\), so the allocated total rate is 1 vehicle/s. A two-second permitted service yields fraction \(1/4\), group amounts \((1,1)\), and exact disaggregated values

\[
m^s=(3/4,1/4,1/2,1/2),
\quad B^s=(3/2,1,1/2,5/2).
\]

If the two C labels carry 2 and 1 persons/vehicle, their served person amount is \(7/4\). If the D labels carry 400 and 600 kg/vehicle, served cargo is 500 kg. The physical allocation did not need four independent control coordinates, but all these different observables remain exact.

At cell j, suppose the C service arrives over the same interval as another 2 vehicles of label \(a_2\), with birth moment 12. The merged group has mass 3, label masses \((3/4,9/4)\), birth moments \((3/2,13)\), and fiber \(K'=(1/4,3/4)\). Serving half of this group gives

\[
m^{ss}=(3/8,9/8),\qquad B^{ss}=(3/4,13/2),
\]

exactly as explicit per-label simulation. The changed fiber shows why one fixed global class mixture would fail even though the physical quotient remains valid. The companion rational calculation checks the displayed values.

### 5.4 Necessary refinements and exact counterexamples

**Only the next destination is too coarse.** Two labels with the same class and paths \(i\to j\to u\) and \(i\to j\to v\) are indistinguishable to the first junction's immediate turn query. After entering j, choose receiving capacity zero toward u and one toward v. A pure first-label state cannot discharge; a pure second-label state can. Equal first-junction aggregates therefore do not imply equal future dynamics. The repair is complete residual-route equivalence or an explicitly refinement-capable future query partition.

**Only physical group totals cannot drive bus service.** If two distinct bus-run tags share a physical group and each has accumulated 1/2 vehicle at its sink, the combined amount is one but neither run has reached the source's near-one completion threshold. A tag-blind threshold would fabricate a completed run. The correct route applies the threshold after separate fiber projections. This is why purpose/service provenance is retained, even when passive during one road segment.

**Equal current speeds do not define a class quotient.** Different response time, footprint, latent hazard or acceleration limits can produce a different next characteristic. Keep class identity unless a stronger invariance proof for all used coefficients and class ledgers is supplied.

**Same class/suffix across different queue positions is not permission to mix the positions.** Different target readiness, head precedence, entry knots or midpoint event boundaries remain active. A group is formed within an existing ordered slab; a queue can be represented by many slabs having the same group key.

**Replanning.** A future tag-specific route/purpose/information policy can split an old group. Apply that policy to the retained fiber and refine the group before its output affects physical control. This preserves the original target but incurs actual refinement work. No permanent label erasure is justified by (B1).

### 5.5 Complexity and the bottleneck that moves

Let \(G\) be the number of distinct class/residual-route groups actually encountered, \(P\) the number of retained virtual queue/entry slabs, and \(C\) the number of physical control changes. Physical head and class/suffix contractions now scale with group support, not with the number of distinct tags carried by a group. A sparse explicit quotient costs the actually populated group–slab pairs; an interval-expression implementation can also avoid their repeated Cartesian products.

Let \(F\) be the size of the retained provenance-fiber representation and \(Q_F\) the work of demanded tag/purpose/service contractions. Total storage/work must include \(F,Q_F\); there is no assertion that they are \(O(G)\). An explicit copied fiber per slab recreates the original explosion. Shared fibers and (B5) can be represented by expression roots, or by exact cumulative provenance functions. Each is a real construction obligation.

Thus B removes repeated *physical* evaluation over behaviorally identical tags, whereas A removes repeated *materialization* even if all tags are behaviorally distinct. The remaining B bottleneck is the number of true residual behaviors and required fiber readouts, especially bus/run thresholds, tag-specific egress, replanning, and any insistence on flat detailed history. This is a viable conditional exact route, not a universal compression theorem.

## 6. Source-ordered streaming comparison

A third, narrower alternative keeps every source operation and row order, but streams events to sink/mark/ledger consumers and uses immutable replayable chunks for detailed observers. This can preserve the original binary64 order if every transform, reduction argument order, row filter, threshold and endpoint bit is preserved. It reduces simultaneous copies and can avoid one global event flattening.

However it still performs one row transform per old logical served row, and the next endpoint overlay still requests expanded rows unless its consumer changes. Streaming without a replayable last-event representation also changes the external checkpoint/query contract. Therefore it is a valuable compatibility/reference lane, but does not by itself remove either Cartesian product's computational work. A and B explicitly change the consumer algebra where streaming alone does not.

| Path | What can disappear | What remains / moves |
|---|---|---|
| A operator + interval expressions | repeated head-row and overlay-row allocation; duplicate mark rows | reachable expression support, query closure/traversal, output expansion |
| B physical quotient + fibers | repeated physical controls over equivalent tags | real group/suffix diversity, provenance evaluation, tag-dependent feedback |
| Source-ordered streaming | coexisting flat copies and some transient buffers | total logical row work and eager interval output |

No row packing or new numeric byte discount establishes any of these stronger consumer-level claims.

## 7. Primary literature actually used

### L1. Cumulative multi-commodity transport

I. Yperman, S. Logghe, C. Tampere, B. Immers, *The Multi-Commodity Link Transmission Model for Dynamic Network Loading*, TRB paper. Primary PDF: <https://www.mech.kuleuven.be/cib/verkeer/dwn/pub/P2006A.pdf>.

Read via Parallel search and fetch. Relevant locations: cumulative route decomposition Eq. (1), inverse cumulative/interpolation discussion around Eqs. (2)–(5), FIFO diverge procedure Eqs. (25)–(26), and route disaggregation Eq. (32) on p. 12. The authors use route-disaggregated cumulative counts and pull the downstream composition from the upstream time with the same cumulative vehicle count. Their FIFO node procedure must preserve earlier entry intervals ahead of later ones. The traffic evolution assumes kinematic-wave/LWR structure with the triangular fundamental diagram and explicitly uses linear interpolation at discrete times. These assumptions do **not** replace MetroFlow's finite-response law or justify erasing its midpoint event knots. Reuse here is the cumulative-composition/disintegration mechanism and the need to retain chronological mixture changes.

Parallel search ID: `search_973439c366ccf09f9f7f483c14250c45`; fetch ID: `extract_906ebffc6f1983c5cac0ed97f09f5526`. Fetch returned no errors. Parent should independently open this PDF before using a final external citation.

### L2. Exact lumpability as a projection condition

L. Horstmeyer and F. M. Atay, *Characterization of Exact Lumpability for Vector Fields on Smooth Manifolds*, Differential Geometry and its Applications 48 (2016), 46–60. Primary author manuscript: <https://arxiv.org/abs/1607.01237>, v2; DOI <https://doi.org/10.1016/j.difgeo.2016.06.001>.

Read via Exa search/fetch. Relevant location: §2.2, Definition 1 and Proposition 1, Eq. (6). Assumptions are smooth manifolds, a smooth vector field, and a smooth surjective submersion \(\pi\). Their criterion is existence of a reduced smooth vector field satisfying \(D\pi_xv(x)=\widetilde v(\pi(x))\). It expresses equality of projected dynamics across fibers. MetroFlow has nonsmooth saturation, event selection and discrete updates, so that smooth theorem is not invoked wholesale. The finite-step condition (B4) and its explicit operation-by-operation proof are the appropriate hybrid counterpart. The paper supplies conceptual/theorem context, not the proof of MetroFlow's closure or a novelty claim.

A separately fetched Qucosa dissertation rendering mixed unrelated metadata with its text. It is not used as a theorem dependency. The primary arXiv manuscript above supplied the needed statement.

## 8. Admission, ownership and next discriminating result

Keep both A and B as exploratory alternatives. The mathematics establishes concrete exact-real constructions and their compatibility limits. It does not select a production architecture, change the original V03 resource/acceptance gates, or upgrade the current completion status.

The next smallest useful theory/measurement object is a **consumer support census** at the blocked original checkpoint: immutable source roots, real endpoint knots, repeated class/suffix supports, distinct contraction masks, and reachable composition ancestry after one source transition. Count these objects without emitting their label × service × slab products. Such a census discriminates whether A's query support or B's behavior/fiber support is actually smaller. It is an evidence request, not a request to repeat the previous packing sequence.

If implementation is subsequently authorized, the first exactness obligation is one complete original transition from head query through interval repacking, marks, service sinks and journey egress, with the original virtual boundaries retained. Exact-real/rational comparison tests the algebra; binary64 and original numerical tolerances require their own evidence. Flat checkpoint export must be tested as a deliberate boundary or replaced with a versioned persistent round trip. None of those tasks was executed in this theory packet.

Skill context used: PhysMath Research Loop 1.3.0 `SKILL.md`, `references/THEORY_LOOP.md`, `references/POLICY_INTEGRATION.md`, `references/SUBAGENT_MODE.md`. The delegated R2/R4/R5 boundary, one author verification pass, preserved original scientific target, typed identity, and absence of a generic strong no-go are applied in the results above.
