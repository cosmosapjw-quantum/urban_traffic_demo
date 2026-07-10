# Feature Specification: JAX Dense-Flow Persistent Chunk Bakeoff

Status: ACCEPTED

## Goal

Move the optional JAX dense-flow probe behind a lazy backend boundary and decide
whether persistent-device multi-step chunks merit a later runtime integration
spec on the RTX 3080 Ti.

## Evidence

- Canonical artifact:
  `artifacts/gpu_dense_flow_bakeoff_20260711/dense-flow-gpu-bakeoff.json`.
- JAX 0.10.2 reports `gpu` on the RTX 3080 Ti 12GB host; process/device warmup
  is measured separately at about 873 ms with memory fraction `0.70`.
- For 512-step frozen-input chunks across seeds 41-43, minimum warm-process
  first-call+copy estimates are 1.125x at 4,096 links and 4.262x at 16,384;
  minimum steady+copy speedups are 12.284x and 37.776x respectively.
- The 65,536-link workload is not admitted: maximum absolute drift is
  `0.0015769`, above the predeclared `0.001` limit.
- Current runtime host synchronization and mutable events/agents within every
  tick are not represented.

## Scope

- Add `metroflow.backends.jax_flow` with no eager JAX import.
- Expose host-step-loop parity mode for the existing measured probe and a
  persistent `device_chunk` experiment mode.
- Move dense-flow workload construction/output comparison to a reusable
  benchmark module without changing runtime flow semantics.
- Add a deterministic three-seed bakeoff result and JSON/Markdown artifact.
- Record device, JAX version, memory-fraction setting, copy, warm-process
  first-call trace/compile/execute estimate, steady timing, parity drift, and
  admission state. Isolated compile cost is not measured.

## Non-goals

- Adding `jax` to `FLOW_UPDATE_BACKENDS` or `SimulationConfig`.
- GPU ownership of `LinkState`, `NodeState`, deterministic replay, or route
  legality.
- PyTorch/libtorch/custom CUDA, multi-GPU, or external-data learning.
- Treating smoke timing as end-to-end runtime validation.

## Acceptance

- Core imports do not load JAX.
- Existing optional JAX dense-flow benchmark behavior and fallback remain.
- Device-chunk parity is evaluated against an explicit `1e-3` long-chunk
  tolerance; sizes above it are rejected rather than described as parity.
- Admission requires three unique seeds, copy-inclusive steady speedup above
  one, warm-process first-call+copy estimate above one, and bounded drift.
- `runtime_flow_backend_authorized` remains false regardless of microbenchmark
  speedup.

## Compact CCoT

Question: Does dense flow justify a GPU runtime backend now?
Evidence: 4,096 and 16,384-link frozen-input 512-step chunks cross over; 65,536
links fails drift and per-tick host-synchronized performance is unmeasured.
Inference: Extract the kernel and validate chunk economics before runtime wiring.
Counterevidence checked: Host-state synchronization can erase device speedup.
Decision: Admit only a persistent-device experiment, not a runtime backend.
Falsifier: Any proposed admitted size fails its warm first-call/copy gate or exceeds 1e-3 drift.
Next action: Park checkpoint-cadence integration as the GPU-lane re-entry
condition and switch immediately to PR48 simulator-only NN feature/label work.

## Review Closure

- `/review-spec`: closed after making the `1e-3` long-chunk drift gate and
  runtime non-authorization explicit.
- `/review-code`: closed after fail-closed non-finite comparison, dynamic JIT
  arguments, baseline clamp parity, and result-contract validation fixes.
- `/review-drift`: closed after replacing isolated-compile wording and aligning
  the artifact/roadmap handoff on PR48 with checkpoint integration parked as a
  GPU-lane re-entry condition.
