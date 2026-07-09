# PR11 C++/CUDA Admission RFC

## Goal

Define the admission gate for future C++/libtorch/custom CUDA work without
adding dependencies, build files, or runtime backend values.

## Evidence

- Hardware atlas card: dense flow, route-score batch, and OD/policy batch are
  possible GPU lanes.
- Runtime benchmark artifact:
  `artifacts/runtime_spine_review/runtime-acceleration-deep-audit.md`.
- Replay/parity artifact: no runtime behavior changes in this PR.

## In Scope

- Create `docs/cuda/CPP_CUDA_ADMISSION.md`.
- Mark PR10 complete and PR11 RFC accepted in roadmap docs.
- Advance project state and next-session handoff to PR12.
- Add docs consistency tests proving PR11 is admission-only and no C++/CUDA,
  libtorch, CMake, or runtime backend config value has been added.

## Out Of Scope

- Do not add C++ sources, CUDA kernels, CMake files, libtorch dependencies, or
  runtime backend values such as `torch_cuda` or `custom_cuda`.
- Do not change Python runtime dispatch, Rust wrappers, benchmark runners, or
  replay schemas.
- Do not claim GPU/CUDA performance validation.

## Public Contract

- APIs/config/artifact keys: unchanged.
- Fallback behavior: unchanged.
- Replay/cache impact: unchanged.
- Admission doc: future implementation can target only one narrow kernel after
  copy/compile-inclusive evidence.

## Acceptance Criteria

- Targeted tests: `tests/test_acceleration_roadmap_docs.py`.
- Dependency/build files do not add C++/CUDA/libtorch/CMake surface.
- Full gates: pytest, ruff, `git diff --check`.
- Review loop max: 3.

## Compact CCoT

Question: Should Metroflow add C++/CUDA/libtorch build surface now?

Evidence: GPU candidates exist, but no single kernel has cleared the evidence
gate with host-device copy and compile/build time included.

Inference: A narrow admission RFC is the correct next step.

Counterevidence checked: RTX 3080 Ti 12GB makes GPU experiments relevant, but
hardware availability does not authorize build complexity.

Decision: Keep PR11 documentation-only.

Falsifier: A dense flow, route-score batch, or OD/policy batch probe proves a
copy/compile-inclusive parent-stage improvement across deterministic workloads.

Next action: Open PR12 state closure.
