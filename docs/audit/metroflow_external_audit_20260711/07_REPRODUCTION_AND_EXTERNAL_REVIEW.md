# Reproduction And External Review Guide

## 1. Integrity First

After extracting the audit ZIP:

```bash
sha256sum -c SHA256SUMS
git bundle verify history/metroflow-all-refs.bundle
git clone history/metroflow-all-refs.bundle metroflow-review
cd metroflow-review
git checkout <packaged_commit>
```

Read `provenance/package_metadata.json` for the packaged commit and environment.
The `repository/` directory is a convenient tracked-file snapshot; the git
bundle is the history authority.

The builder normalizes ZIP member order/timestamps but does not promise
byte-identical archives: git bundle packing and host environment capture can
vary. It fails closed on a dirty or shallow repository, ref drift during the
build, unsafe path names, tracked symlinks/gitlinks, bundle/ref mismatch, or any
manifest/checksum mismatch.

## 2. License Stop

There is no root license. Do not redistribute source or artifacts until the
owner resolves licensing and donor provenance. Integrity packaging is not a
license grant.

## 3. Base Environment

Expected host baseline:

- Ubuntu 24.04
- Python 3.12 in repository-local `.venv`
- NumPy base dependency
- optional Rust toolchain/maturin
- optional JAX CUDA 13 + Optax on RTX 3080 Ti 12 GB

Python dependencies and the complete environment are not locked; Rust
dependencies use tracked `Cargo.lock`. Record all resolved versions in every
reproduction.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

## 4. Critical Self-Drive Probes

The 2026-07-11 result and the 2026-07-12 remediation are different revisioned
claims. Run both before any performance experiment. Do not run the historical
expectation against the remediated working tree and then describe the mismatch
as an audit failure.

### 4.1 Historical Negative Control

The executable audit probe was retained in audit delivery commit
`e428de848184f9b079e47f027f0b205c80b9d443`. Check out that exact revision:

```bash
git checkout e428de848184f9b079e47f027f0b205c80b9d443
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 3 --expect-stalled
```

The command uses the public `SimulationInitBundle`, `SimulationControl`, RNG,
and four-value `simulation_step` contract. It diagnoses the frozen source
baseline `96e54ca907babe6425212ac2e088615687549d72`: queues fill, but turn
demand, outflow, and movement remain zero. `--expect-stalled` fails closed if
that exact historical blocker is not reproduced.

### 4.2 Remediated Bounded Check

Check out the later remediation revision recorded as `packaged_commit` in
`provenance/package_metadata.json`, then run:

```bash
.venv/bin/python -m metroflow.benchmarks.runtime_self_drive_probe \
  --scenario-seed 41 --steps 20 --expect-closed
```

The 2026-07-12 developer run reports 16 generated trips, 51,886 compiled turns
(45,544 permitted), 15 completed trips, one explicit no-route failure, no
remaining active agents or queue mass, passing runtime invariants at every
tick, and exact equality between per-link queue mass and active-agent counts.
This is `INTERNALLY VERIFIED` functional evidence for one small deterministic
scenario. It is not a 100k-city benchmark, full traffic-model validation,
observed-data validation, or independent reproduction. Review the exact claim
boundary and remaining blockers in
[10 Runtime Closure Remediation](10_RUNTIME_CLOSURE_REMEDIATION_20260712.md).

## 5. Rust Verification

```bash
cargo fmt --all --check
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target cargo test --workspace
CARGO_TARGET_DIR=/tmp/metroflow-cargo-target \
  .venv/bin/python -m maturin develop --release \
  --manifest-path crates/metroflow-rust/Cargo.toml
.venv/bin/python -m pytest \
  tests/test_meso_core.py \
  tests/test_flow_engine_rust_backend.py \
  tests/test_routing_rust_backend.py \
  tests/test_active_agent_rust_backend.py -q
```

Do not infer speed from parity. Use a copy-inclusive parent-stage benchmark.

## 6. Optional JAX/GPU Verification

```bash
.venv/bin/python -m pip install -e '.[dev,jax]'
XLA_PYTHON_CLIENT_MEM_FRACTION=.70 .venv/bin/python - <<'PY'
import jax
print(jax.default_backend())
print(jax.devices())
PY
```

Re-run canonical GPU commands from `docs/harness/VALIDATION_LEDGER.md` and use a
new output directory. Record driver, CUDA compatibility, JAX/Optax versions,
compile timing, steady timing, copy timing, synchronization policy, raw metric
rows, and checksums. Never overwrite the historical artifact before comparing.

## 7. City Visual Review

Use layer-isolated images as diagnostics:

- roads only;
- zones only;
- POIs only;
- morphology contact sheet;
- connectivity/repair links;
- full extent and largest-component focus.

Inspect topology and images separately. A legal graph can look implausible; a
plausible image can conceal disconnected or illegal topology.

## 8. External Review Questions

### Functional

- Where is route position transformed into per-turn demand?
- Is vehicle mass conserved across source insertion, links, sinks, failures,
  and event capacity changes?
- Which runtime owns medium/slow demand, accessibility, and land-use updates?

### Numerical

- Are float32/float64 semantics identical across NumPy, Rust, and JAX?
- Does a speedup include conversion, synchronization, and checkpoint costs?
- Are cache invalidation and recomputation counters consistent with the actual
  state dependency?

### Scientific

- Which outputs have observed-data calibration and a held-out validation set?
- Are structural morphology thresholds project regression gates or empirical
  distributions?
- Does route choice include calibrated heterogeneity or only deterministic
  generalized cost?

### Provenance

- Can the donor/import ancestry be established independently?
- Can every canonical artifact be regenerated from a commit, command, locked
  environment, and retained sufficient statistics?
- What license authorizes redistribution?

## 9. Acceptance Order For Future Work

1. functional closure;
2. conservation and full-state replay;
3. one multirate authority;
4. synthetic scale benchmark;
5. accelerator bakeoff;
6. observed-data calibration and external reproduction.

The 2026-07-12 remediation supplies bounded internal evidence for item 1 only;
it does not promote items 2 through 6 to complete. Reversing this order risks
optimizing a model that has not yet established its central behavior at the
claimed scale and fidelity.
