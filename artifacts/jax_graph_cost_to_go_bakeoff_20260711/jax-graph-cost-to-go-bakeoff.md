# JAX Graph Cost-To-Go Bakeoff

Diagnostic experiment only. It does not authorize runtime NN routing.

- Decision: `inconclusive`
- Mean graph/control normalized-MAE ratio: 1.0581
- Passing model seeds: 0/3
- Accuracy gate passed: false
- Repeat deterministic: false
- Runtime NN backend authorized: false

| Seed | Row-local MAE | Graph MAE | Ratio | Row params | Graph params |
|---:|---:|---:|---:|---:|---:|
| 41 | 0.456222 | 0.470127 | 1.0305 | 3873 | 4257 |
| 42 | 0.391902 | 0.463352 | 1.1823 | 3873 | 4257 |
| 43 | 0.40912 | 0.39336 | 0.9615 | 3873 | 4257 |

## Compact CCoT

Question: Does directed graph context improve held-out-map cost-to-go prediction?
Evidence: Fixed three-seed row-local and graph-aware JAX models on the exact PR49 holdout.
Inference: The fixed MAE ratio and determinism gates decide only whether graph signal is supported.
Counterevidence checked: No runtime replay, route legality, real-city data, or checkpoint integration is measured.
Decision: inconclusive; the fixed graph accuracy hypothesis is not supported.
Falsifier: The graph model misses accuracy, provenance, GPU, parameter-fairness, or repeat gates.
Next action: Stop graph-NN tuning and require an owner-selected acceleration lane step-back.
