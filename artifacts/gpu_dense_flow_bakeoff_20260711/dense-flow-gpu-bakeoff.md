# Dense Flow GPU Bakeoff

Diagnostic microbenchmark only. It does not authorize a runtime JAX flow backend.

- Device: `NVIDIA GeForce RTX 3080 Ti` (gpu)
- JAX: `0.10.2`
- XLA memory fraction: `0.70`
- JAX runtime warmup: 873.454 ms
- Steps per persistent chunk: 512
- Max absolute drift tolerance: 0.001

| Links | Runs | Min warm first-call+copy estimate | Min steady+copy speedup | Max abs diff | Chunk review-ready |
|---:|---:|---:|---:|---:|:---:|
| 4096 | 3 | 1.125 | 12.284 | 0.000861168 | yes |
| 16384 | 3 | 4.262 | 37.776 | 0.000876904 | yes |
| 65536 | 3 | 13.537 | 85.331 | 0.0015769 | no |

## Compact CCoT

Question: Does dense flow justify a GPU runtime backend now?
Evidence: Three-seed warm-process first-call/copy/steady timing plus parity measurements; 4,096 and 16,384 pass, while 65,536 is rejected for drift.
Inference: A review-ready chunk size does not establish per-tick host-synchronized speedup.
Counterevidence checked: Import/device discovery is separate, inter-invocation compile-cache reuse is unmeasured, chunk inputs are constant, and runtime events/agents synchronize on host ticks.
Decision: Keep runtime_flow_backend_authorized=false; park checkpoint-cadence integration as the GPU-lane re-entry condition.
Falsifier: Host-synchronized integration retains speedup and replay parity at an explicit checkpoint cadence.
Next action: Switch immediately to PR48 simulator-only cost-to-go feature and label contracts.
