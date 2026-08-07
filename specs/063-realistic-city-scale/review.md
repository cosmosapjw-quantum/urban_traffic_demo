# PR63 Review Record

Status: implementation approved; performance/product gate failed closed
Date: 2026-07-13

## /review-spec

The implementation covers the fixed 1k/10k/100k, seeds 17/29/41, legacy and
realistic matrix. City generation, full initialization/fixed runtime,
paired-budget runtime, and realistic substage profiling use separate fresh
processes. The default, generator behavior, replay authority, and optional
backend import boundaries are unchanged.

## /review-code

Finding loop 1: the first worker sampled RSS after runtime and instrumented
realistic substages inside the generation ratio. Generation, fixed runtime,
paired-budget, and stage-profile phases are now isolated. The generation gate
uses city-authority-only process RSS, and stage wrapper overhead cannot affect
the legacy/realistic ratio.

Finding loop 2: the initial time-budget loop counted a tick that completed
after its deadline and allowed `0 >= 0` to pass. It now counts only completions
before the deadline and requires the legacy workload to complete at least one
tick. Requested and actual citizen/trip counts are recorded; underfilled 100k
workloads fail comparability.

Finding loop 3: the first implementation combined worker, aggregation, CLI,
and reporting in one 1,162-line module. Worker instrumentation and artifact
rendering are separate modules behind a stable facade. Unattributed
blueprint/CSR/final-assembly time remains visible, and a fingerprint-verifying
loader permits reporting-only regeneration without rerunning the 15-minute
matrix. Regression tests cover missing/duplicate rows, budget mismatch,
zero-tick vacuity, population underfill, all-seed Rust admission, subprocess
PID isolation, artifact tampering, and accelerator import firewall. No
unresolved findings remain.

## /review-drift

Question: Does realistic-city scale evidence authorize promotion or one narrow
generation-core follow-up, without mistaking nested timing for product quality?

Evidence: the canonical `42`-run artifact has report fingerprint
`149571c18552e5cc655a0c33844fe487a7b6165cea808b1c55a3b47655f5278e`.
At 100k, generation is `2.553`, `2.582`, and `2.770x` legacy. Realistic
citizen counts are `61,993`, `61,655`, and `62,604`; legacy is `62,500` for
every seed. Equal-budget realistic throughput is `16,17,16` ticks versus
legacy `20,21,21`. RSS ratios (`0.850-0.867`) and fixed 20-tick latency ratios
(`1.081-1.101`) pass. No eligible generation stage reaches 30 percent on all
seeds.

Inference: the realistic path fails independent generation, population, and
throughput gates. The measured generation cost is distributed rather than
dominated by one Rust-eligible stage.

Counterevidence checked: cumulative RSS, stage-wrapper timing bias, seed or
budget mismatch, deadline overshoot, zero-tick vacuity, empty routing demand,
population underfill, ratio-of-medians masking, 1k/10k shared map extent, auto
style discontinuity at 100k, artifact hash mismatch, and PR62 morphology
failure.

Decision: approve the diagnostic harness and canonical artifact. Reject default
promotion and do not open a Rust generation core. PR64 must record `BLOCKED`.

Falsifier: any in-process RSS comparison, non-paired seed, changed runtime
default, unrecorded workload difference, threshold tuning, or performance
claim that overrides PR62 morphology failure.

Next action: close PR64 as `BLOCKED` without changing the default, then redesign
street fabric and capacity realization under a new specification.

## Gates

- targeted scale tests: `10 passed`;
- related initialization/runtime/replay tests: `62 passed`;
- canonical matrix: `894.31 s`, parent maximum RSS `229,980 KiB`;
- full repository: `777 passed in 557.86s`;
- Ruff, artifact fingerprint reload, and diff checks: passed.
