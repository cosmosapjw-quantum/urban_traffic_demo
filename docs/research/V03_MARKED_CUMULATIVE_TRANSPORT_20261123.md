# MetroFlow V03: marked cumulative-rank transport, constructive model R0

**Status:** project-derived theorem, exact real arithmetic; not a claim of a previously unknown theorem in the traffic literature. This is a separately versioned **scientific model candidate**, not a silent change to original V03. Background: Newell (1993), *A simplified theory of kinematic waves, III: Multi-destination flows* (https://ideas.repec.org/a/eee/transb/v27y1993i4p305-313.html); Daganzo (1994), *Cell Transmission Model: Network Traffic* (https://its.berkeley.edu/publications/cell-transmission-model-network-traffic); Bar-Gera & Carey (2017), *Representation requirements for perfect FIFO verification* (https://www.sciencedirect.com/science/article/abs/pii/S0191261516305458). The last source cautions that many practical network models need an explicit network-wide FIFO check.

## Definition and modeling contract

On each oriented link ℓ choose a **cumulative vehicle-equivalent rank** \(u\in[0,U_ℓ]\) in units of vehicles. Let \(A_ℓ(t),D_ℓ(t)\) be nondecreasing, right-continuous entering and exiting vehicle-equivalent counts with \(0\le D_ℓ(t)\le A_ℓ(t)\), \(A_ℓ(0)=D_ℓ(0)=0\). Let \(h_ℓ(u)=(r(u),c(u),b(u),w(u),\ldots)\) carry route suffix, vehicle class, entry/birth time and nonnegative marked weight vector \(g(u)=(1,g_{\rm persons},g_{\rm cargo},\ldots)\). Variable occupancy or boarding at an internal service node requires an explicit source/update term, never silent reweighting of already transported ranks.

The current vehicle stock is the rank interval \((D(t),A(t)]\); a service advances only the exit prefix endpoint \(D(t)\), subject to demand/sending-receiving and finite-response eligibility. A time-dependent mark is not allowed inside this theorem unless its evolution is explicitly carried as a source.

## Proposition 1: exact marked FIFO ledger and residence identity

For any integrable component mark \(g_j:[0,U]\to[0,\infty)\), define

\[
I_j(t)=\int_0^{A(t)}g_j(u)\,du,\qquad
E_j(t)=\int_0^{D(t)}g_j(u)\,du,\qquad
Q_j(t)=\int_{D(t)}^{A(t)}g_j(u)\,du.
\]

Then \(I_j=E_j+Q_j\) exactly; no served rank can overtake another within this link. If \(\alpha(u)=\inf\{t:A(t)\ge u\}\) and \(\omega(u)=\inf\{t:D(t)\ge u\}\), allowing \(\omega=+\infty\) for unreleased mass, then

\[
\int_0^TQ_j(t)\,dt=
\int_0^{A(T)}g_j(u)
\bigl[\min(T,\omega(u))-\alpha(u)\bigr]_+\,du.\tag{1}
\]

For the birth-time mark \(\beta(u)\), the corresponding first-moment queue ledger is \(B_j^Q(t)=\int_{D(t)}^{A(t)}\beta(u)g_j(u)du\), which obeys the same inflow-minus-outflow identity.

**Proof.** \([0,A]=[0,D]\mathbin{\dot\cup}(D,A]\) since \(D\le A\); additivity of the integral proves conservation componentwise, for every route indicator or class mark as well. The served rank set \([0,D(t)]\) is nested as \(t\) increases, so serving a larger rank without the smaller one is impossible: linkwise FIFO. Each \(u\) belongs to the queue at time \(t\) exactly when \(\alpha(u)\le t<\omega(u)\), except measure-zero time endpoints. Because \(g_j\ge0\), Tonelli permits exchanging the time and rank integrals; integrating that indicator over \([0,T]\) yields the clipped residence duration in (1). Identical reasoning with \(\beta g_j\) applies when its absolute integral is finite. \(\square\)

At junctions, if each departing marked rank enters an intended downstream link with unchanged conserved marks and an explicitly booked node queue/transfer, internal link fluxes cancel in the network conservation sum. This is **conditional** on physically legal routing and joint capacity; linkwise FIFO does not establish global FIFO at a merge.

## Proposition 2: bounded representation-growth criterion

Suppose \(h(u)\) and every mark queried by the physical closure are constant on \(K\) cumulative-rank intervals, with endpoint counts and prefix integrals stored once. Then any number \(H\) of partial serves can be represented by changing \(D(t)\) alone, without constructing \(KH\) packet compositions. Each class/route occupancy and additive mark moment is a difference of two prefix queries, executable in \(O(\log K)\) per query with binary search, with immutable source storage \(O(K)\) plus a separately charged event/history \(O(H)\) if observations require all events. This conclusion holds **only** for closures expressible from those recorded mark prefix functionals and eligibility conditions; if class-specific motion or age distributions change, the sufficient marks must be enriched, or the original path retained.

**Proof.** For a piecewise-constant \(g_j\), its prefix function \(G_j(x)=\int_0^xg_j(u)du\) is piecewise linear with the same \(K\) breakpoints. Hence \(Q_j(t)=G_j(A(t))-G_j(D(t))\). Serving a prefix changes \(D(t)\) but not any immutable breakpoint or mark. A sorted breakpoint search costs logarithmic comparisons. Recording \(H\) distinct observed events is independent of the state representation; the worst-case \(O(KH)\) explicit packet-split product is absent from this representation, not from arbitrary other V03 workspaces. \(\square\)

## A constructive warning about insufficient closures

Total mass and the first birth/ready-time moment are not generally sufficient for finite-response admission. The two ready-time measures \(\delta_0+\delta_2\) and \(2\delta_1\) both have mass 2 and first moment 2, but by time \(t=1.5\) have eligible masses 1 and 2. The positive corrective construction is to retain **a marked readiness distribution or cumulative rank breakpoints**, not to discard age information in favor of only two moments. This example is a project-specific counterexample, not a universal no-go for all compressed traffic descriptions.

## Exact rational worked case, symbolic verification and IEEE boundary

Two source spans have vehicle mass 3 and 4 and person weights 2 and 5. At \(A=7,D=4\), person inflow is \(3\cdot2+4\cdot5=26\), departed persons are \(3\cdot2+1\cdot5=11\), queue persons are \(3\cdot5=15\). Wolfram Language evaluated the corresponding piecewise integrals to \(\{26,11,15,\mathrm{True},\mathrm{True}\}\). IEEE 754 reassociation is not exact: \((0.1\cdot0.3)\cdot0.7-0.1\cdot(0.3\cdot0.7)=-3.469446951953614\times10^{-18}\) in the checked floating calculation. Therefore real-algebraic equality is **not** byte equality of the old V03 multiply sequence. The shadow model below is versioned, with physical/observable comparison required before any production admission.

**Scientific relevance:** cumulative link occupancy and residence time can feed congestion, accessibility and subsequent land-use/demand changes directly. That preserves the original map→traffic→accessibility→development coupling instead of treating individual array rows as physical agents. A complete V03 replacement still requires a valid coupled finite-response/hazard/route solver and original full-day acceptance.