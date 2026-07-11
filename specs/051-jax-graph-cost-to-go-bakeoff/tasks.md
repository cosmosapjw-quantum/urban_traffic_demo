# Tasks

- [x] T001 Add Optax to the optional JAX extra and verify lazy core imports.
- [x] T002 Add RED config, gate, corpus-provenance, artifact, and optional-JAX tests in `tests/test_jax_graph_cost_to_go_bakeoff.py`.
- [x] T003 Implement deterministic canonical graph corpus and train-only normalization in `src/metroflow/benchmarks/jax_graph_cost_to_go_bakeoff.py`.
- [x] T004 Implement fixed row-local and recurrent graph-aware JAX/Optax models with compile/steady timing.
- [x] T005 Implement three-seed plus repeat evaluation, per-map/state metrics, decision gate, and compact artifacts.
- [x] T006 Run the canonical RTX 3080 Ti bakeoff and verify deterministic serialization separately from nondeterministic training output.
- [x] T007 Run `/review-spec`, `/review-code`, and `/review-drift` with at most three bounded fix loops.
- [x] T008 Run full Python gates, stage exact files including ignored specs/artifacts, and commit.
