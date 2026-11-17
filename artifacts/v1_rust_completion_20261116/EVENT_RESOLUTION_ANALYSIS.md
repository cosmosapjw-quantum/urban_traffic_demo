# Positive sub-ULP event durations: independent numerical analysis

Date: 2026-11-16 UTC. Base commit: `7b5e518f6c098ed831551da4e66d980addf80dd8`.
Inspected working-tree code: `src/metroflow/packet_network.py` and `crates/metroflow-rust/src/v1_road.rs`.
This is a derived analysis with direct binary64 counterexample calculations, not an implementation PASS or a complete simulation acceptance.

## Result

A strictly positive event duration can be smaller than the representable increment of the local clock. Allowing such an event can be a controlled numerical-resolution treatment, provided it changes a finite discrete state and its omitted time is bounded. It is **not exact real-arithmetic evolution** merely because the existing mass-allocation expression is retained. Unchanged-clock processing can repeatedly emit positive mass whose subtraction rounds away from another head or a receiver resource.

The narrow acceptable claim is finite progress plus a quantified time/rate/moment error budget, separately verified mass/storage conservation tolerances and checkpoint rollback. A bound on omitted time alone is not a proof of identical later trajectories near readiness or parent-release thresholds.

## Existing transition

At a junction the code computes, in binary64,
`h = min(dt-cursor, future_ready-cursor, head_mass/rate, receiver_free/dest_rate, free_space/space_rate)`.
It rejects `h<=0` and `cursor+h==cursor`.

For each positive rate, it computes
`fraction=min(1, rate*h/packet_mass)`,
snaps fraction to one when `1-fraction<1e-14`, and applies the same fraction to part masses and birth moments. Receiver increments are debited by subtract-and-clamp. Readiness has a separate existing `1e-10` seconds comparison tolerance. Neither snapping nor tolerance is a new proposed physical rule.

The concrete reported blocker (0.125 followed by mass 1e-20 at unit rate) is consistent with floating-point clock resolution. It does not establish a model-level impossibility.

## Strong counterexample, numerically checked

Take cursor=1, h=2^-54, and two active sink heads with rates one:
A has mass h; B has mass one. A retires completely. For B:
- served mass = h > 0;
- `fl(1-h)=1`, so the stored remainder stays one;
- `fl(1+h)=1`, so the cursor stays one.

Repeat with N=2^20 initially queued tiny A heads. Every iteration has genuine head retirement, yet B emits an additional N*h = 2^-34 = 5.820766091346741e-11 while its mass remains one. A later full drain emits that one as well. Thus head retirement guarantees finite iterations, not exact mass or horizon-rate preservation.

The receiver analogue uses free space=1: `fl(1-h)=1` after every small arrival. A later full-size arrival can leave actual admitted mass 1+2^-34 with the stored free-space counter zero. Subtract-and-clamp is not an exact resource proof. Existing relative conservation tolerances can mask this size of residual; successful validation must not be described as exact conservation.

This is a pre-existing local splitting/subtraction rounding mode that the old stall check stopped before repeated stagnant steps. Permitting those steps newly exposes its accumulation. Finite packet/event budgets prevent infinite amplification but do not make the error vanish.

## Finite-progress condition (derived)

For an unchanged-clock step require all of:

1. h is finite and strictly positive. Underflow to h=0 remains a numerical failure; do not synthesize an arbitrary duration or delete a tiny head.
2. Execute the original allocation expressions, including existing caps/snapping and deterministic order. Do not force a limiting packet to retire merely because the quotient was the smallest limit.
3. Verify an actual discrete change after the candidate allocations: at least one FIFO position increases, or a receiver's previously enabled mass/space gate crosses to its disabled state. The current gates require both free and free_space > 1e-13. A computed intention to saturate, a tiny decrease that leaves the gate open, or identical before/after bits is insufficient.
4. Preserve the original finite event/storage budgets and transactional rollback.
5. Add h to a conservative omitted-time accumulator and reject before committing if the explicit numerical error budget would be exceeded.

Proof: let P be the number of packets remaining in the initial incoming queues plus the number of receiver mass/space gates still above the threshold. During this junction pass, new transfers are buffered elsewhere until after the pass, incoming positions never decrease, and receiver resources never increase. Each accepted zero-clock step lowers P by at least one. Therefore the number of such steps is at most initial packet count plus twice the number of receiving resources. This proof requires checking the actual gate transition, not rounding a resource to zero for convenience.

For finite nonnegative cursor c and round-to-nearest, `fl(c+h)=c` implies h no larger than half the gap to the next float (tie behavior depends on parity). If c<dt, a conservative bound is:
`E = sum(stalled h) <= N_stall * ulp(dt)/2`.
This bound can be loose; measure E directly. A positive representable future time or dt cannot itself have a positive gap smaller than the next representable cursor increment, so the pathological limiter is a head/resource event rather than a distinct representable clock boundary.

## Clock and observable error bounds (derived, with assumptions)

Let E be the exact sum of positive durations for which the local cursor did not advance. Let D bound ordinary rounded advancing additions. Define A=E+D. Compare a fixed emitted event trace with a virtual clock that also accumulates those durations.

- Local time displacement is at most A. If the omitted durations are never debited, the virtual serviced horizon can reach dt+E (plus ordinary addition error).
- If S_i bounds the sending rate of incoming group i, extra nominal service opportunity caused by ignored duration is bounded by S_i*E. A receiver with nominal rate bound R_j has an analogous R_j*E bound. This is a rate-budget bound, not a proof that individual flow allocations/identities are unchanged.
- Actual fractional arithmetic adds separate error. In normal arithmetic without overflow/underflow, the multiply/divide fraction calculation has relative error bounded by gamma_2=2u/(1-2u), u=2^-53, before clipping. The existing near-one snap can add approximately 1e-14 times the head mass. Underflow and heterogeneous multi-part multiplication need their own checks.
- Let U_abs bound floating-point spacing over the absolute timestamp range. Computing `t+cursor+h/2` introduces at most approximately U_abs through its two rounded additions (plus the underflow bound for h/2). For fixed nonnegative emitted masses totalling M, the timestamp-only first-moment change is bounded by M*(A+U_abs). Waiting and transfer-hold time use 1-Lipschitz max/linear functions and admit the corresponding local-time bound.
- If masses also differ by total absolute amount DeltaM, add an absolute-time scale times DeltaM to an absolute exit-moment bound. Do not claim M*E controls the full error when masses or event identities differ.
- At t=86400 and cursor=0.125 the absolute timestamp spacing is 1.4551915228366852e-11 seconds. Even a correctly tracked local h=1e-20 gives equal binary64 absolute start/end values. Equal recorded timestamps are consequently not by themselves evidence of dropped mass; they also do not certify exact event duration.
- Readiness, packet/turn changes and parent CDF thresholds are discontinuous decisions. A small clock bound does not furnish a uniform bound on the entire subsequent network trajectory. Threshold-neighbouring regression cases are necessary.

A budget B should satisfy the already accepted time tolerance and corresponding rate/storage/moment tolerances, e.g. `S_i*B <= allowed_mass_error_i`. Choose/report it explicitly rather than adopting the existing readiness epsilon as if it were already an approved global-error tolerance. Record count alone must not set the scientific tolerance.

A plain `E += h` can itself lose small terms. For a rigorous nonnegative upper bound, use directed-upward accumulation, e.g. after each positive add take `nextafter(fl(E+h), +infinity)`, or a verified floating-point expansion with an explicit final outward bound. Track count, maximum h, bound E, and affected junctions; aggregate conservatively across ticks for cumulative reports. A compensated sum without a documented error bound is an improvement, not automatically a certified upper bound.

## Local compensated-clock alternative

If the permitted time/rate budget is too small, retain a local two-component clock or duration debt and subtract it from the remaining horizon and future-event distances using compensated subtraction. It must enter every clock-dependent boundary and observable consistently, not only `dt-cursor`. This prevents silently allocating an extra E of service time. It does not remove the mass-splitting counterexample: tiny positive served mass can still leave a large head/resource unchanged after binary64 subtraction. That issue needs its own bounded rounding residual or more accurate local mass accounting.

Do not add nextafter(cursor,+infinity) as a fake event duration while retaining old rate*h: that injects time without matching allocated mass. Do not erase tiny masses or replace a small h by an arbitrary floor.

## Minimal validation obligations

- The reported 0.125/1e-20 example completes with preserved tiny mass, original birth moment and correct event order.
- The two-head repeated-small-service counterexample and receiver-space analogue have measured error below the declared budgets; include a deliberately over-budget case that fails with its last valid checkpoint intact.
- Positive h but rate*h underflow for a nonlimiting head does not count as progress. A no-head-retirement/no-gate-closure case fails rather than looping.
- Check representable gate transition, tied minima, nextafter clock boundaries, duplicated ready times, a future-ready head immediately around the threshold, and parent release around a receipt threshold.
- Compare Rust and Python under the same policy. Matching two implementations proves policy parity, not real-arithmetic exactness.
- Run the actual failed-state resume and report the measured stall count/time bound and conservation residual; complete the full simulation acceptance separately.

## Verification provenance

Direct Python binary64 and Fraction calculations verified the numerical examples; an independent code-review agent reproduced the two-head counterexample. No implementation files were changed. Wolfram was not needed for these exact powers-of-two checks. The SHA-256 values in EVENT_RESOLUTION_ANALYSIS.json identify the inspected working-tree files before any later implementation changes.

## Selected refinement: activate a compensated local clock only at the first stall

The parent subsequently selected this narrower implementation direction. Preserve the original binary64 path until a finite positive h satisfies fl(cursor+h)=cursor and at least one existing computed fraction retires a head. Thereafter represent elapsed local time by a normalized pair (hi,lo), debit the low component in horizon/future distances, and preserve the original mass/rate/part order. Implementation ownership remains with the road agent.

A general error-free TwoSum is:
`s=a+b; bb=s-a; e=(a-(s-bb))+(b-bb)`.
For finite additions without overflow, under round-to-nearest/gradual underflow, s+e equals a+b exactly as real numbers. Do not substitute FastTwoSum unless its magnitude precondition is proved for every call.

A transparent pair-plus-duration update is:
`(s,e)=TwoSum(hi,h); (v,f)=TwoSum(lo,e); (hi_new,lo_new)=TwoSum(s,v)`.
Its exact invariant is:
`hi_new+lo_new = hi+lo+h-f`.
The third-order discarded term is f. Consequently an outward-rounded sum R of |f| bounds the accumulated representation residual relative to the exact sum of the chosen floating-point h values. If `lo+e` is instead evaluated by one ordinary addition, that addition's rounding error must be included. R does not include error in selecting h itself from floating-point boundary differences or rate quotients.

E=sum(collapsed h) is now a diagnostic of durations successfully processed below the high-component resolution; **it is no longer omitted time** when the debt is consumed. Do not label E as the compensated-clock error. A separate cap on E may restrict the fallback's operational domain, but borrowing the readiness tolerance 1e-10 does not by itself prove mass, moment, or trajectory accuracy. The relevant clock error is R plus the bounded boundary/observable arithmetic errors.

Termination must use compensated remaining time, not `hi<dt`. Require either positive progress of the normalized represented pair or the verified finite discrete progress described above; if even the pair remains unchanged, record the lost duration in R and enforce its bound. Signed zero changes do not count as progress. Reject a genuinely nonpositive h; do not create progress by advancing one ULP. If no rates remain and the clock jumps to a future ready timestamp, set the pair consistently to that timestamp and zero low component, only after verifying it is in the future of the represented pair.

`remaining=(dt-hi)-lo` is convenient but rounded. The first subtraction is exact by Sterbenz when hi is between dt/2 and 2*dt, as in the actual failure; the second has at most half an ULP error. Outside that range, include both subtraction errors or compute the distance using TwoSum(dt,-hi) and retain its residual. Future-ready distances need the same treatment. Readiness comparisons and local midpoint/hold calculations must account for lo consistently; collapsing hi+lo first discards its purpose at sensitive boundaries.

### Actual-value arithmetic check

Using cursor=8.221431926605018, h=6.538054381607992e-16, dt=10:
- ordinary cursor+h remains 8.221431926605018;
- the first compensated pair is (8.221431926605018, 6.538054381607992e-16), f=0;
- compensated remaining rounds to 1.7785680733949818;
- adding that remaining value yields (10.0, -1.2328376614294725e-17), f=0;
- therefore **even the actual failing values** produce hi==dt with positive remaining time 1.2328376614294725e-17. That last duration must still be processed if rates remain.

Standalone Python TwoSum calculations checked these pair identities with exact Fraction arithmetic. A further checked counterexample is hi=1, lo=2^-54, h=2^-108: the new pair stays (1,2^-54), with discarded f=2^-108. All operands are normal binary64 values. Thus the compensated pair itself can fail to advance, requiring actual discrete progress plus its residual bound or an explicit failure. Additional mandatory edges are hi==dt with lo>0, active-path h larger than hi (general TwoSum requirement), and a future boundary affected by lo. The two-head and receiver subtraction counterexamples remain relevant: correcting time does not make binary64 mass splitting exact.


