# Exact storage and simulation continuation contract

Baseline: `7b5e518f6c098ed831551da4e66d980addf80dd8`.
Requested scope: finish Rust ownership and actual simulation, then publish.
The V03 scientific gates remain 100,000 residents, all declared demand, three
cities, three 24-hour runs, restart/refinement, 7,200 s wall and 8 GiB peak RSS.
Full repository CI, integration and final release remain deferred.

## Delayed stages

An access row is `(leg, m, b, d)` with finite positive mass, birth time `b`,
and nonnegative delay `d`. The production predicate is exactly
`b + d <= clock + 1e-10`, evaluated with the existing f64 operation order.
For source law atoms `(d_j,w_j)`, the existing products `m*w_j` and
`(m*w_j)*b`, and `d_j+hold`, remain unchanged.

For an ordered row sequence `R = B_1 ++ ... ++ B_k`, stable filtering obeys

```
filter(P, R) = filter(P, B_1) ++ ... ++ filter(P, B_k).
```

Consequently an immutable block whose minimum **already evaluated** `b+d`
exceeds the existing threshold can be retained without inspecting its rows.
Other blocks are filtered in their original row order. Callbacks producing
offers or completion receipts execute in that same order. No law-order
assumption is available: delays may be unsorted. No mass/time binning or
floating-point reassociation follows from this representation change.

Flattening the blocks reproduces the old ordered row stream. With unchanged
owner transitions and a frozen pre-tick input, induction over ticks gives the
same row values, ledger updates and completion clocks. This is a derived
representation argument; actual implementation must additionally pass oracle,
old checkpoint byte, branch/restart, partial-drain and failure tests.

The real-arithmetic mass and birth-moment identities were independently checked
with Wolfram Language in `DELAY_IDENTITIES.wl`. That check does not establish
f64 bitwise equivalence. Runtime comparisons supply the implementation evidence.

## Resource policy

`legacy_records` retains the previous raw-row guard and checkpoint binding.
The explicit `bounded_bytes_v1` policy separates logical row diagnostics from
allocated stage/history/road storage and candidate/transient work. Its identity
must differ; old files cannot be silently reinterpreted under a new guard.
The raw checkpoint wire schema can remain unchanged when rows stream in the
same order. No second full materialization is required for serialization.

Storage estimates must state their coverage, sharing and peak-transaction
assumptions. They are not measured RSS. The local runner separately applies
the existing 8 GiB address-space limit and measures peak RSS. A conservative
owner quota failure must be distinguished from actual RSS exhaustion.

## Independent work and acceptance

- Journey: immutable stage blocks, exact retirement, history storage accounting.
- Road: bounded candidate/transient accounting and exact stable grouping.
- Engine/frontend: explicit policy binding, native route latency and truthful
  campaign/failure progress reporting.
- Root: independent cross-policy/restart tests, actual local build and simulation,
  source/evidence binding, plan update and publication.

Native numerical work stays in Rust. Python supplies marginal configuration,
CLI/process supervision, artifact I/O and diagnostics; its previous numerical
path remains the explicit scientific oracle.

The actual simulation result determines the outcome. A short prefix or an
execution receipt alone cannot satisfy the full-day, replay, refinement or
resource gates. A reproducible model/numerical/implementation/resource failure
is preserved with the last valid state and its distinct cause.
