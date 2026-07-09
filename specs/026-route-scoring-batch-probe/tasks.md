# PR06 Tasks

- [x] Add RED tests for route scoring benchmark schema, invalid config, K>1
  metadata timing, path-size utility preservation, reroute scoring batch shape,
  optional JAX fallback, and no runtime GPU backend admission.
- [x] Implement route scoring benchmark config/result dataclasses.
- [x] Implement deterministic route scoring fixture and output fingerprint
  helpers.
- [x] Implement K>1 candidate metadata/path-size scoring probe using existing
  route candidate authority.
- [x] Implement reroute scoring batch probe using existing baseline/rust
  fail-closed reroute policy wrappers.
- [x] Add benchmark-only optional JAX dense-score timing/fallback metadata if it
  changes the decision card; otherwise record it as deferred.
- [x] Update roadmap/project docs with PR05 commit hash, PR06 status, and
  decision boundary.
- [x] Run `/review-spec`, `/review-code`, and `/review-drift`; apply up to three
  fix loops.
- [x] Run targeted tests, full pytest, ruff, and `git diff --check`.
- [x] Commit as `test(routing): add route scoring batch probes`.
