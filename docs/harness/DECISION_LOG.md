# Decision Log

## 2026-07-09: Runtime Acceleration Anti-Drift Guardrails

Status: accepted

### Context

Runtime benchmark instrumentation was refined through multiple slices. The deep
audit showed a stable conclusion across 1-step and 2-step eager suites:

- `active_agent_pool_write` is review-ready and dominates active-agent cost.
- `active_agent_candidate_selection` is not review-ready.
- `route_candidate_refresh` remains large, but its nested route potential/path
  build stages are both below the 0.30 review threshold.

### Metacognitive Self-Ask

Question: Are we repeatedly adding timing counters without changing the next
implementation action?

Evidence: The last two benchmark suites changed the explanation of
`active_agent_update`: first to allocation, then to pool write. That changed the
next action away from NN/JAX scoring and toward state-write/data-layout work.

Inference: One more split is justified only for `active_agent_pool_write`; more
route timing splits are not justified until pool-write is addressed or falsified.

Counterevidence checked: `active_agent_candidate_selection` remained near 3.5
percent in both 1-step and 2-step eager suites, so NN/JAX route-choice scoring is
not currently the hot-path fix.

Decision: Use `docs/harness/RUNTIME_ACCELERATION_DECISION_GUARDRAILS.md` as the
control document for future acceleration work and `/review`.

Falsifier: If a broader suite with longer horizon or larger K makes
candidate-selection or route metadata review-ready while pool-write falls below
threshold, reopen the NN/JAX path.

Next action: Split `active_agent_pool_write` into typed-array pool replacement
and plugin-memory dict update before implementing a backend optimization.

## 2026-07-09: GPU/NN Lane Kept As Watchlist, Not Runtime Default

Status: accepted

### Context

The user explicitly wants GPU+NN acceleration to remain an active project goal.
The benchmark evidence does not support making it the immediate hot-path fix.

### Decision

Keep JAX/GPU and NN surrogate lanes open as benchmark-gated watchlists:

- JAX/GPU: route scoring/metadata batches and dense flow update at larger scale.
- NN surrogate: dynamic-potential cost-to-go labels and route scoring labels.

Do not add PyTorch/libtorch/custom CUDA dependencies in the next slice.

### Review Note

Any `/review` that argues for GPU/NN must identify the exact scoring or dense
numeric stage it targets and show that it is not deterministic state mutation.

## 2026-07-09: Pool-Write Sub-Breakdown Redirects Next Slice

Status: accepted

### Context

`active_agent_pool_write` was split into:

- `active_agent_pool_array_write`
- `active_agent_plugin_memory_write`

The 1-step and 2-step eager suites both kept the parent `active_agent_pool_write`
above the 0.30 review gate. The plugin-memory substage was larger than the
typed-array substage but stayed below the 0.30 gate.

### Compact CCoT

Question: Should the next implementation be Rust pool-array write planning,
plugin-memory data-layout reduction, or NN/JAX scoring?

Evidence: In the regenerated eager suites, `active_agent_pool_write` stayed
review-ready, `active_agent_pool_array_write` stayed near 0.09 to 0.10 mean
share, `active_agent_plugin_memory_write` stayed near 0.26 to 0.28 mean share,
and `active_agent_candidate_selection` stayed near 0.03 to 0.04 mean share.

Inference: The parent pool-write stage remains the real active-agent issue, but
the first subproblem is Python plugin-memory mapping churn, not typed-array pool
replacement and not route-choice scoring.

Counterevidence checked: `active_agent_plugin_memory_write` does not clear the
0.30 review gate, so it is not a standalone accelerator target; it is a
data-layout cleanup target inside the review-ready parent stage.

Decision: Reduce dict-heavy selected-candidate metadata writes before opening a
Rust pool-array backend slice.

Falsifier: If metadata reduction does not lower parent pool-write cost, or if a
broader deterministic suite makes typed-array pool replacement the dominant
substage, reopen Rust pool-array planning.

Next action: Move hot selected-candidate diagnostics out of per-slot plugin
memory where possible, while preserving UI/replay-visible metadata behavior.
