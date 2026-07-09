# PR05 Tasks

- [x] Add RED tests for dense flow probe schema, invalid config, Rust parity,
   optional JAX timing/parity, and no runtime JAX backend admission.
- [x] Add regression coverage for JAX runtime failure fallback, JAX steady-state
   timing validity, JAX input/output copy timing, and `turn_demand`
   fingerprint sensitivity.
- [x] Implement dense synthetic flow fixture generation and benchmark result
   fingerprint/diff helpers.
- [x] Implement benchmark-only JAX optional probe with lazy import and compile
   vs steady-state timing fields.
- [x] Update roadmap/project docs with PR05 status and decision boundary.
- [x] Run `/review-spec`, `/review-code`, and `/review-drift`; apply up to three
   fix loops.
- [x] Run targeted tests, full pytest, ruff, and `git diff --check`.
- [x] Commit as `test(flow): add dense flow acceleration probe`.
