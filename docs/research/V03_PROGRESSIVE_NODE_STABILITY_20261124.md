# A local stability certificate for multi-sender marked FIFO nodes

Source basis at 8020a60: docs/research/V03_BOTTLENECK_COUPLED_MEASURES_20261123.md §9.3, docs/research/V03_REMAINDER_MATHEMATICS_20261124.md Theorem B, docs/v1/t03/NODE_CONTRACT_KO.md, src/metroflow/packet_network.py _rates, and crates/metroflow-rust/src/v1_road.rs rates. The derivation below is project-derived. The companion oracle checks finite rational examples.

Fix a matched junction phase with the same FIFO heads and positive sender priorities \(w_i\), each with sending limit \(S_i\) in vehicles/s and fixed nonnegative turn fractions \(\beta_{ij}\). Receiving row \(j\) has capacity \(R_j\) in vehicles/s. Sink movements have no receiving constraint. Write \(q_i=w_i y_i\) and set \(H_{ji}=\beta_{ij}w_i\), \(b_j=R_j\). Include one cap row \(H_{ii}=w_i\), \(b_i=S_i\) per sender. Priorities are dimensionless. Hence \(y_i\) and \(b_j\) have rate units and \(H\) is dimensionless. Distinguish sender cap rows from receiving rows even if IDs coincide. All bounds are finite and nonnegative.

## Tight-row certificate and stability

A feasible \(y\ge0\) has the progressive-filling certificate when each \(i\) has a tight row \(j\) with \(H_{ji}>0\) and \(y_k\le y_i\) for all positive contributors \(k\) to \(j\). Progressive filling raises the active senders at a common level from zero and freezes all active contributors when their row becomes tight. Frozen senders cannot change a later tight row after freezing, and all earlier frozen levels are at most the current one. This constructs the certificate in at most \(n\) stages. Every remaining sender has its own cap, ensuring a finite next level. The certificate also expresses max–min fairness: any feasible increase of \(y_i\) must decrease a contributor \(y_k\le y_i\) of a tight row.

The certificate is unique. Suppose two certified vectors \(y,z\) differ. Choose a differing \(i\) minimizing \(\min(y_i,z_i)\), swapping the solutions if necessary so \(y_i<z_i\). The tight row at \(y\) containing \(i\) would violate feasibility at \(z\) unless another contributor \(k\) had \(z_k<y_k\le y_i\). This contradicts the choice of \(i\).

For fixed \(H\), let \(F,A\) be the frozen and active sets along an allocation branch. For a row \(j\) with active slope \(d_{j,A}=\sum_{i\in A}H_{ji}>0\), the next candidate level and its capacity gradient are

\[
 \ell_j = \frac{b_j-\sum_{k\in F} H_{jk}y_k}{d_{j,A}},
 \qquad
 \nabla_b\ell_j = \frac{e_j-\sum_{k\in F}H_{jk}\nabla_b y_k}{d_{j,A}}.
\]

Select the smallest candidate. Feasibility of the current common level ensures the selected level is at least that common level. Along any fixed sequence of minimizing rows and freeze sets, \(y\) is affine and the path inequalities are linear in \(b\). There are finitely many paths. At a tie, the limits of any adjoining path solutions remain feasible and certified: along a fixed path the chosen certificate row for each sender is fixed, tightness is closed, and the contributor levels obey closed inequalities. The uniqueness proof identifies these limits with the tie solution. Thus integrating the piecewise-constant gradients along the capacity segment gives

\[
 \|y(H,b')-y(H,b)\|_\infty\le K_H\|b'-b\|_\infty .
\]

One may use the maximum 1-norm of the reachable gradient rows as \(K_H\), restricted to paths crossing a segment if those paths are known. A conservative bound is \(B_n\) from \(B_0=0\), \(B_{k+1}=\max(B_k,(1+UB_k)/d)\), with \(U=\max_j\sum_i H_{ji}\) and \(d=\min_{j,i:H_{ji}>0}H_{ji}\). The recursive gradient permits materially tighter local bounds when this coarse constant is large.

## Varying composition and threshold error

Let \(H'\) have the same positive support and sender identities as \(H\). For \(y=y(H,b)\) form \(b^*=b+(H'-H)y\). Then \(b^*=b-Hy+H'y\ge0\), all row slacks at \(y\) are identical, and the ordering comparisons in each bottleneck certificate still concern the same contributors. Hence exactly

\[
 y(H',b^*)=y(H,b),\qquad
 \|y(H',b')-y(H,b)\|_\infty
 \le K_{H'}\bigl(\|b'-b\|_\infty+\|H'-H\|_{\infty\to\infty}\|y(H,b)\|_\infty\bigr).
\]

With fixed priorities, multiply sender-specific rate bounds by \(w_i\). If comparing changed priorities, also account for the product \(q_i=w_i y_i\). The row-sum norm and normalized rate bound have the appropriate units. A common lower positive coefficient bound yields a uniform constant over a family of phases with the same support. Positive support is substantive. For one sender with positive sending cap, a zero-supply destination and arbitrarily small positive turn fraction to it force zero shared-head rate, whereas removing that turn permits positive service if the remaining destination is open. Preserve this physical transition as a phase boundary.

In exact real arithmetic, an allocator that freezes all positive active contributors of any row within a nonnegative threshold \(\tau_j\) of tightness, or freezes a sender within its one-sender cap threshold, admits the same certificate at slightly lowered \(b^\dagger\). For each row used to freeze a sender, lower its cap to the attained row flow. It remains at that attained flow because every user has already frozen or freezes at this stage. Each change lies in \([0,\tau_j]\), all other rows remain feasible, and each sender receives a tight certificate. Zero sending is already certified by its own cap at zero. Thus the exact-real threshold output equals exact progressive filling at \(b^\dagger\), and the same \(K_H\) converts measured backward capacity errors to rate error. The current Python and native Rust source implement the stated early-freeze threshold pattern with binary64 updates. This proof isolates the threshold effect. Binary64 can additionally create rate/level mismatches or feasibility residuals, which need their own numerical certificate.

## Constructive use with the marked-rank model

For matched phases with fixed priorities and cumulative departure rank increment \(\int q_i\,dt\), a prefix mark with Lipschitz constant \(L_i\) inherits an error at most \(L_i\int|\Delta q_i|\,dt\), plus any initial rank error multiplied by \(L_i\) and any uniformly bounded profile perturbation. When marks are instead constrained to a destination, use the same joint retained profile or directly bound \(|q_i\beta_{ij}-q'_i\beta'_{ij}|\le \beta'_{ij}|q_i-q_i'|+ q_i|\beta_{ij}-\beta'_{ij}|\). Rank densities of persons or original birth moments retain their own physical units. Routing labels and birth/age correlations need the corresponding mark profile. The bounds provide a local use criterion for compressed continuous models that preserve FIFO order, legal turns and active head support. For fixed \(H\) and affine \(b(t)\), the same branch inequalities give linear equations for the earliest allocation switch, allowing affine-rate integration up to that root or any earlier physical guard. The existing native phases with fixed capacities and finite-response eligibility retain their event laws. No whole-city error or speed-up follows without checking branch margins, matched phases and upstream/downstream feedback.

The rational oracle uses receiving rows \((1,1,0),(0,1,1)\), which come from weights \((1,2,1)\) and a middle sender with \(1/2,1/2\) turns. With loose sending caps and receiving \((2-\epsilon,2+\epsilon)\), the level vector is \((1-\epsilon/2,1-\epsilon/2,1+3\epsilon/2)\). At exact tie it is \((1,1,1)\). The sharp local \(\ell^\infty\) gain for these receiving variations is \(3/2\). The finite Fraction check covers 300 capacity pairs and 1,024 grid points with same-support composition shift and threshold-adjusted replay, including zero caps.

## Literature context

Daganzo (1995) supplies a multi-commodity network CTM and junction reference. Wright, Gomes, Horowitz and Kurzhanskiy give a lane-geometry interpretation of partial FIFO. The theorem above addresses MetroFlow's exact-real weighted progressive allocation locally, with turn support explicitly held fixed. [Daganzo](https://doi.org/10.1016/0191-2615(94)00022-R) · [Wright et al.](https://arxiv.org/abs/1601.01054)
