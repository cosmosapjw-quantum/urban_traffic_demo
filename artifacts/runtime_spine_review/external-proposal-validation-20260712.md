# External Proposal Validation - 2026-07-12

Status: **accepted after corrective review; product and backend promotion remain blocked**

Source proposal: `46f0fd7`

Reviewed state: `eb042bc`

## Review Result

The proposal closes the historical zero-turn-demand stall, but it was not safe
to accept unchanged. Adversarial review found and corrected:

1. Fractional sending/receiving tokens could phase-starve legal movement.
2. A residual of exactly `1.0` could mint service on a closed link.
3. Baseline and Rust handled invalid turn indices differently.
4. Incident clearance did not force route refresh/reroute.
5. Route memory was not bound to packed trip identity or validated against the
   final destination before first movement.
6. Runtime replay omitted controls, the actual RNG key, and step count.
7. Current-state invariants did not prove the prior-to-next queue transition.
8. NaN queue/progress values could pass invariant checks.
9. JAX dense flow retained obsolete storage and multiplicative-cost equations.
10. Cadence rerouting recomputed identical graph work per active vehicle.

The corrective commits are `44d1145`, `505bb11`, `e30af45`, `368e719`, and
`eb042bc`.

## Measured Evidence

- Ten deterministic seeds, 64 ticks each: 158 trips, 148 completed, 10
  explicitly classified `no_route_candidate`, zero final active/queue mass,
  and zero observed link-level agent/queue delta.
- Population 10,000 / seed 41: 3,105 trips close at tick 156. Same-tick reroute
  caching reduces measured runtime from 77.1 s to 16.0 s without changing the
  terminal counts.
- Population 100,000 / seed 41: 31,069 trips initialize, but a 240 s bounded run
  reaches only tick 128 with 10,626 active vehicles. All observed invariants
  pass; closure and operational throughput remain unvalidated.
- RTX 3080 Ti dense-flow parity is restored. At 16,384 links and 32,768 turns,
  16-step JAX steady execution is about 1.20 ms versus 12.50 ms for NumPy, but
  compile and copies make the first JAX run about 67.6 ms. Maximum output drift
  is `1.43e-5`.
- Rust flow remains exact in the measured fixture but its list/copy boundary is
  much slower for the dense 16,384-link probe.

All timings are local diagnostics, not stable cross-machine benchmarks.

Final repository gates: Python/JAX-enabled `pytest` 623 passed, Rust workspace
53 passed, installed-extension Python/Rust parity 35 passed, Ruff passed, Cargo
format passed, and `git diff --check` passed.

## Compact CCoT

**Question:** Can the pulled proposal be accepted as the new authoritative
runtime and reopen acceleration promotion?

**Evidence:** Small and 10k generated workloads close deterministically after
the corrective commits. Replay inputs and transition mass are now bound. The
100k run remains incomplete at the 240 s limit, physical link traversal remains
coarse, and JAX only wins after compile/copy amortization.

**Inference:** Accept the corrected functional closure, but keep product-scale
and backend-default claims closed.

**Counterevidence checked:** Multi-seed flow, asymmetric fractional capacity,
incident closure/clearance, malformed route identity/destination, replay
tampering, Rust parity, JAX GPU parity, and 1k/10k/100k scale probes.

**Decision:** Merge only the corrected branch. Preserve Python/NumPy authority.
Keep Rust/JAX optional and keep NN/custom CUDA outside runtime authority.

**Falsifier:** Any deterministic replay mismatch, transition mass violation,
unclassified failure, or copy-inclusive accelerator regression reopens this
decision.

**Next action:** Profile the remaining 100k cadence route build/decision cost,
then define physical link traversal before interpreting tick completion as
traffic realism.
