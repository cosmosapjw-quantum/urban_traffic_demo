# Conservative entry projection — independent scoped review

Date: 2026-11-17. Base HEAD: `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`.
Scope: one independent C9 scientific/code pass over `entry_review.diff`, the current design/theory documents, and live implementation. No source ownership, no whole-repository audit, no repeated test suite. The live Rust category-count reservation correction was included in this review.

Snapshot SHA-256:

- `src/metroflow/entry_projection.py`: `eb51625b68c1d36a0c1230c6a1fccbc130af1b05aae18d4891d13abf27b169b8`
- `crates/metroflow-rust/src/v1_road.rs`: `47179f9973ed66f909159377e069cd65d8f822f8f956154ccfc75b73a19846aa`
- `crates/metroflow-rust/src/v1_engine.rs`: `583c3541cc163a8261dd0ae5a2dbb2d0e4383533a758f5f157d968b4681b40a8`

## Finding requiring a small correction

**P2 — Failed campaign receipts retain the initial projection diagnostics.**

Location: `tools/run_v1_local_acceptance.py:328`, `:398–399`, `:400–424` (reviewed snapshot).

The worker records `driver.runtime.projection_diagnostics()` immediately after construction. It refreshes that field only after successful completion. If one or more projected steps succeed and a later step fails due to memory/record limits or numerical representability, the exception path saves the last valid checkpoint and failure metrics but never refreshes `result['entry_projection']`. Its final JSON therefore reports the constructor's zero input/output/cohort counts and zero local bound rather than the runtime's latest validated road proposal. The attached scope string does not identify these as initial-state diagnostics, so the receipt is misleading in precisely the blocked large-city runs this change is intended to diagnose.

Impact: diagnostic/provenance error; no demonstrated mutation of the physical state, conservation law, or saved checkpoint. The native diagnostics themselves already have an explicit non-checkpointed, latest-proposal scope.

Minimum correction: refresh projection diagnostics in common finalization whenever a whole-native driver was successfully constructed, or refresh them in the relevant exception path. Preserve the existing scope/checkpointed fields; do not relabel these counters as cumulative or necessarily equal to the rolled-back checkpoint. Constructor failure must remain safe when no driver exists.

Evidence status: source/control-flow verified. No campaign was rerun in this independent pass; this finding follows directly from the assignment sites and exception flow. The parent was notified during review.

## Scientific and implementation checks from source inspection

- The sweep uses integer active counts per immediate movement and barriers on changes of positivity, not mass thresholds. Concurrent starts/ends at the same endpoint are processed together. Tiny positive blocked movements therefore create barriers; mere multiplicity changes do not. No new mass/class/route pruning was found in the projection construction.
- Original equal-time atoms enter one `combine` packet, preserving the existing exchangeable law; different atom times remain separate, with the point packet preceding the right interval segment. Category barycentres inside one interval cohort are not passed back to exact interval splitting.
- Rust categories `(tag, offset)` preserve full interned routes, including later divergence; Python uses `(tag, remaining)`. Aggregated mass, birth moment, and relative entry moment yield the stipulated real-arithmetic conservation. Positive piece underflow causes explicit failure. The retained live row allocation now reserves resulting category count, fixing the excessive mixed-cohort capacity risk from the initial diff.
- The stated W1 proof is valid for the exact conditional mean on a bounded segment. It is a local measure cost bound in veh·s; it supplies no nonlinear network travel-time/trajectory bound. The theory explicitly acknowledges signal sensitivity and downstream route divergence. Floating-point conservation/bound interpretation still requires the stated numerical tolerances; outward accumulation is not a general interval-arithmetic proof.
- Projection runs at the incoming boundary after motion admission marks are computed, retaining existing finite-response motion and initial class weights. Subsequent service composition can differ, as documented.
- `h=0` takes the old packet path and does not append an identity suffix. Positive widths bind policy name and IEEE-754 width bits; the whole engine, native road adapter, frontend, release driver, CLI, and checkpoint binding are connected. Both bounded-byte and legacy whole-engine identity paths were inspected.
- Rust boundary/piece allocations are fallible with explicit preflight envelopes, output rows enforce the record budget, and retained output allocations are charged. State is built as a proposed transition and installed after success. Projection diagnostics are updated only after a validated road proposal and deliberately remain outside checkpoint state. No new atomicity defect was identified in the reviewed flow.

These are source-inspection findings, not fresh execution PASS claims. Existing Python/native/replay/resource results reported by the parent were not independently rerun here.

## Nonblocking limitations and documentation clarifications

1. **Rust integration cost is O(P K), not merely overlap-sensitive.** At `crates/metroflow-rust/src/v1_road.rs:1714–1740`, each of K protected edges scans all P inputs for point atoms and each segment scans all P intervals, allocating an n-capacity transient pieces buffer. The support sweep itself is O(P log P), but disjoint intervals or many genuine support changes can retain quadratic scan work even when the number of actual overlaps is linear. This does not invalidate the representation or conservation, and the full-city target is already explicitly incomplete. Minimum present action: state the Rust O(P K) scan limitation in performance evidence; optimize active-interval traversal only if actual local measurements make it necessary. Do not claim the Python overlap-oriented integration complexity for Rust.
2. **Point-law wording is ambiguous.** `CONSERVATIVE_ENTRY_PROJECTION_DESIGN_KO.md:16` and the theory's phrase “독립 packet 순서” may suggest each original Part retains an independent packet, whereas the intended and implemented old law combines equal-time atoms. Minimum clarification: equal-time atoms remain one exchangeable packet; distinct times remain ordered separately. No algorithm change is warranted.

## Scoped disposition

No P0/P1 physics, default-path, support-barrier, category-preservation, or checkpoint-binding defect was identified in this pass. Correct the campaign failure-receipt diagnostic field before relying on its blocked-run projection numbers. The complexity and wording notes do not introduce a new acceptance gate. Local projected execution can proceed with the existing explicit numerical-approximation status and existing tolerances. The 100k-resident/full-demand 24-hour target, the three-city repeated campaigns, and global network accuracy remain incomplete; this scoped review does not promote them to accepted or proven.

## Resolution recorded by integration owner

The P2 failure-receipt finding was fixed in the CLI common finalization. The new regression failed on the old control flow and passed after correction. Final Python suite: 88 passed. Final native-related suite: 164 passed. Actual Valley resource failure at 26010 s preserved nonzero latest projection diagnostics in VALLEY_PILOT.json. The atom wording and Rust O(PK) complexity clarifications were applied to the design/theory. Full-city acceptance remains BLOCKED.
