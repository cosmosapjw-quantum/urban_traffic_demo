# PR08 Tasks

- [x] Add RED tests for optional torch extra, no core torch import, baseline
  surrogate fit/predict determinism, torch fallback metadata, and runtime
  backend rejection.
- [x] Implement `metroflow.learning.surrogate` dataclasses and baseline NumPy
  fit/predict helpers.
- [x] Implement lazy `torch_optional` experiment backend fallback metadata.
- [x] Export public harness APIs from `metroflow.learning` without eager torch
  import.
- [x] Update roadmap/project docs with PR07 commit hash, PR08 status, and
  experiment-only authority boundary.
- [x] Run `/review-spec`, `/review-code`, and `/review-drift`; apply up to three
  fix loops.
- [x] Run targeted tests, full pytest, ruff, and `git diff --check`.
- [x] Commit as `feat(learning): add optional route surrogate harness`.
