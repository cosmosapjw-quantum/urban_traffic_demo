# PR03 Dynamic-Potential Cache Amortization

## Goal

Improve the runtime dynamic-potential cache without relaxing route correctness.
The first slice is Python/NumPy baseline only: prune stale cache entries when the
runtime route-cache signature changes, expose deterministic cache-size/prune
counters, and keep replay behavior authoritative.

## Scope

- Add runtime route-potential cache pruning keyed by the existing network,
  flow-generation, incident-generation, and routing-policy signature.
- Preserve the current fail-closed backend contract:
  `routing_backend="rust_cpu"` remains explicit and `auto` may fall back.
- Record counters that explain cache amortization:
  `dynamic_potential_cache_pruned_total` and
  `dynamic_potential_cache_entry_count`.
- Update the accelerated runtime PR list and decision notes.

## Non-Goals

- Do not remove `runtime_flow_generation` or incident generation from the cache
  signature.
- Do not reuse stale potentials across flow/event generations.
- Do not add Rust, JAX, torch, CUDA, or new backend logic.
- Do not change route legality, candidate ranking, or active-agent movement.

## CCoT Record

- Question: Can route-potential cache amortization improve without risking stale
  routing state?
- Evidence: Current runtime cache keys include flow and incident generations,
  but stale entries can remain in the runtime cache after those generations
  change.
- Inference: Pruning stale entries is the safe first amortization step because
  it makes invalidation explicit and bounds cache growth before more aggressive
  reuse is considered.
- Counterevidence checked: Removing flow generation would increase reuse but
  could reuse costs after queue/capacity changes, violating deterministic route
  authority.
- Decision: Add pruning and observable counters only.
- Falsifier: If replay parity changes, route candidates change for unchanged
  inputs, or cache hits disappear within the same current signature, revert.
- Next action: Add RED tests for stale-entry pruning and current-signature cache
  reuse.

## Acceptance Criteria

- Stale runtime dynamic-potential cache entries are removed when the state
  signature changes.
- Current-signature entries remain reusable within a refresh pass.
- Route tick counters include prune deltas.
- Runtime stats record current cache entry count.
- Targeted tests, full pytest, ruff, and whitespace gates pass.
