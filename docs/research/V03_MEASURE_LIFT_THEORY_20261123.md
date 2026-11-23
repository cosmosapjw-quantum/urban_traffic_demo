# Constructive theory for V03 resource relief

## S03: stable partition normal form of a finite FIFO source

Define an ordered sequence (Q=(a_1,\ldots,a_n)) with marks \(a_i=(\mathrm{leg}_i,m_i,b_i,\tau_i)\) and expiry predicate \(d_i(t)=\mathbf1\{b_i+\tau_i\le t\}\). The original StageQueue stores consecutive blocks of arbitrary occupancy \(1\le n_k\le B\), with \(B=256\), and an immutable block-prefix history. For a fixed source sequence let \(P_B(Q)\) be the consecutive canonical blocks \(Q_{1:B},Q_{B+1:2B},\ldots\), with a final possibly partial block.

**Lemma (stable FIFO partition equivalence; project-derived).** If (i) the per-row expiry predicate depends only on the row and clock, (ii) aggregate block min/max bounds are exactly recomputed from its rows, and (iii) the callback traverses blocks and rows in original insertion order, then \(Q\mapsto P_B(Q)\) commutes with ordered retirement: the ordered expired sequence and ordered survivors are identical at each clock, and every tagwise additive physical moment (vehicle/person/freight mass and birth moments) is unchanged. No assumption of equal byte capacity or Arc aliasing is made.

**Proof.** The canonical blocks form a disjoint consecutive partition of the same ordered index set. For each index the predicate \(d_i(t)\) is unchanged. The two output sequences are therefore the unique stable subsequences selected by \(d_i=1\) and \(d_i=0\), irrespective of partition. Recomputed min/max ready bounds only short-circuit all-true/all-false blocks and cannot change any selected row. Any moment is a sum of the same exact ordered terms: the iterator order is preserved and no arithmetic factor is altered. Repeated retirement proceeds inductively because the remaining ordered rows are equal after each step. □

**Storage bound (derived, not an allocation claim).** With \(n=|Q|\), the canonical row payload reserve is at most \(B\lfloor n/B\rfloor+\rho(n\bmod B)\), where \(\rho(r)=0\) for \(r=0\) and \(\rho(r)=\min(B,2^{\lceil\log_2\max(4,r)\rceil})\) otherwise. A reference canonical block consumes one payload backing per contiguous group. Thus the number of blocks is \(\lceil n/B\rceil\), whereas an adversarial fragmented representation may have \(n\) blocks. Actual Vec capacities and live snapshots must be measured and allocated conservatively; a compaction cannot be credited until the old physical owners are actually dropped.

**Boundary:** This is an exact *representation* lemma for StageQueue, not a new traffic continuum theory. It does not assert that a lower count reduces process RSS or V03 admission in every state. A later stage must execute it in Rust and test actual guards, including coexistence with immutable snapshots.

Finite assertion and replay oracle: artifacts/v03_measure_lift_20261123/S03_PARTITION_ORACLE.json. This mathematical proof does not derive a global complexity guarantee for the full traffic engine.
