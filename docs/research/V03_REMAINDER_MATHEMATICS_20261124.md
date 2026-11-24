# V03 constructive remainder and marked-network theory
Date: 2026-11-24. Status: project-derived (proof) and numerically checked (finite binary64 cases).

## Theorem A: exact source-to-final packet packing
Consider an immutable ordered Part sequence P=(p_1,...,p_N), a fixed binary64 factor f, each Part having route key (tag,offset), mass m, birth first moment b, and endpoint bit-pair (a,z). The current eager algorithm first creates portion(P,f), retaining exactly those rows with fl(m*f)>0 and setting their mass to fl(m*f) and birth to fl(b*f). The subsequent PacketParts::pack returns Uniform if the positive subsequence is nonempty, all endpoint *bits* agree and all route indices fit u32; otherwise it returns Mixed (including empty).

**Claim.** A two-pass direct packing algorithm can first count and classify surviving rows without allocation and then populate only the final CorePart vector or Mixed Part vector, producing the identical Part payload bits, source order and packet representation as eager portion followed by pack whenever both calculations use the same deterministic per-row binary64 operations and allocations succeed.

**Proof.** Pass 1 visits the same ordered source, tests precisely fl(m*f)>0 and matches packet intervals by bit representation and keys using the same u32 rule. This determines the exact length and type that the eager pack would see. Pass 2 visits in the same order and performs fl(m*f), then fl(b*f) only for positive survivors, copying unchanged endpoints and route keys. No reordering, reassociation, or summation is introduced. The empty case remains Mixed(empty). Thus every kept value and representation is identical. QED.

**Constructive allocation result.** With N input rows and n_+ positive survivors, eager portion provisionally reserves 48N bytes of Part (based on source length), and Uniform conversion concurrently reserves another 24n_+ bytes of CorePart. The direct constructor needs only 24n_+ for Uniform or 48n_+ for Mixed, eliminating an actual temporary 48N Part owner. The source Arc and new output still coexist, so resource accounting must retain both. The bound is on nominal row payload, not the allocator metadata or process peak RSS. A very small positive source mass can underflow to zero, so filtering must precede birth multiplication.

## Theorem B: conditional marked conservation across a traffic network
Let a finite directed graph have linkwise ordered vehicle ranks with cumulative entering and departing counts A_l(t),D_l(t), 0<=D_l<=A_l, nondecreasing. Let g_{l,j}(u)>=0 be an integrable label/mark for vehicles, persons, cargo or birth first moment. Define link stock
 Q_{l,j}(t) = Integral_{D_l(t)}^{A_l(t)} g_{l,j}(u)du.
At every node, impose *booked* matching of incoming and outgoing labelled flux: each internal transfer is either assigned to exactly one legal outgoing edge with conserved mark, or remains in an explicitly counted node queue; any boarding/production or mark update is explicitly entered as a source S_j.

**Claim.** If all link and node ledgers are finite, the total marked stock obeys
 sum_l [Q_l,j(T)-Q_l,j(0)] + sum_v [N_v,j(T)-N_v,j(0)]
 = ExternalIncoming_j(0,T) - ExternalOutgoing_j(0,T) + S_j(0,T).
**Proof.** On each link the cumulative stock is inflow minus outflow by additivity of integrals over its ordered rank interval. At each node, matching makes every internal transfer appear once as exiting a link and once as entering a downstream link or a node queue with the opposite sign. Sum over the finite graph and cancel all internal terms, leaving only the external boundary and declared sources. QED.

This result is constructive: link congestion, class/route-specific occupancy, birth moments, and residence-time observables can use stable cumulative mark functions rather than materializing new per-service packet copies, provided the physical motion closure and finite-response eligibility are expressible through retained marks and their support. Linkwise FIFO alone does not establish merge/junction network-wide FIFO: explicit priority/cohort rules are required. This proposition is a conditional project formulation, not a novel general traffic theorem or a proof of native V03 equivalence.

Context: Newell 1993 multi-destination cumulative waves (https://scispace.com/papers/a-simplified-theory-of-kinematic-waves-in-highway-traffic-ivm7nnruzm); Daganzo 1995 multicommodity CTM (https://scispace.com/papers/the-cell-transmission-model-part-ii-network-traffic-22gpoce9k9); Yperman et al. multi-commodity LTM (https://www.mech.kuleuven.be/cib/verkeer/dwn/pub/P2006A.pdf). These sources provide background, not a global novelty claim.

Finite double-precision oracle: artifacts/v03_remainder_rebuild_20261124/L03_FINITE_ORACLE.json. Production Rust implementation and large original-demand test follow at L04-L06.
