# PR03 Tasks

1. Add RED tests for stale potential-cache pruning and current-signature cache
   reuse.
2. Implement runtime potential-cache key inspection and pruning in
   `metroflow.sim.routing_runtime`.
3. Surface deterministic route tick counters for prune and cache-entry counts.
4. Update the acceleration PR list with PR03 scope/status and anti-drift note.
5. Run `/review-spec`, `/review-code`, and `/review-drift`; apply up to three
   fix loops.
6. Run targeted tests, full pytest, ruff, and `git diff --check`.
7. Commit as `perf(routing): amortize dynamic potential cache`.
