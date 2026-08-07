# Feature Specification: Realistic City Scale And Hardware-Fit Closure

Status: in progress

## Goal

Measure the realistic synthetic city pipeline at production population scales
without changing generator behavior, and decide whether performance permits
default promotion or justifies one narrower Rust generation probe.

## Requirements

- Run every measurement in a fresh Python subprocess so peak RSS and stage
  timings are not contaminated by previous matrix entries.
- Fix the canonical matrix to population targets `1_000, 10_000, 100_000`,
  seeds `17, 29, 41`, modes `standard` and `realistic_synthetic_v1`, and the
  Python/NumPy baseline runtime.
- Use eager deterministic trip generation and measure 20 runtime ticks.
- Measure the exact city-authority boundary used by
  `build_initial_simulation_state`, full initialization, runtime wall time,
  runtime stage timings, graph sizes, trip count, and Linux peak RSS in KiB.
- Isolate `city_authority`, `fixed_steps`, `time_budget`, and
  `city_stage_profile` in separate fresh processes. The generation RSS gate
  uses only the city-authority process; runtime allocation cannot contaminate it.
- Split realistic city-authority time into terrain, urban form, hierarchical
  skeleton, continuous local fabric, planar blocks, block land use, topology
  compilation, zoning compilation, and quality evaluation.
- At population 100k, run both modes under the same per-seed wall budget and
  record only ticks completed before the deadline. A zero-tick legacy result is
  non-evidence and fails the throughput gate.
- Record requested and actual citizen/trip counts. A 100k runtime pair is
  comparable only if both modes actually create 100,000 citizens under the
  same eager-trip and active-agent-capacity contract.
- Write JSON, Markdown, HTML, and manifest artifacts with explicit diagnostic
  claim status and deterministic configuration provenance.
- Preserve generator fingerprints, runtime defaults, replay contracts, and
  optional backend import firewalls.

## Performance Gates

At population 100k, every fixed seed must satisfy:

- realistic city-authority wall time at most `2.0x` legacy;
- realistic peak RSS at most `1.5x` legacy;
- realistic 20-tick parent runtime wall time at most `1.25x` legacy;
- realistic progressed ticks under the paired wall budget not below legacy.

The performance gate is separate from PR62 plausibility. Passing performance
cannot override the failed morphology gate.

The 1k and 10k requests both resolve to `synthetic_smoke`; 100k resolves to
`synthetic_100k` and a different auto style. The matrix therefore measures
three population/initialization workloads but only two generated map extents.

## Rust Admission Gate

Only `hierarchical_street_skeleton`, `continuous_local_fabric`, and
`planar_blocks` can open a follow-up Rust generation probe. One stage must
consume at least 30 percent of the realistic city-authority boundary for all
three 100k seeds in the separate stage-profile phase. Blueprint/CSR/final
assembly time remains visible as unattributed overhead. PR63 records the
decision only; it does not add Rust code.

## Claim Boundary

This is a controlled local diagnostic benchmark, not hardware-independent
validation. Timing and RSS values describe the recorded host and workload.
Smoke tests, one seed, or a nested-stage improvement cannot authorize default
promotion. PR64 must also consume the independent PR62 plausibility result.
