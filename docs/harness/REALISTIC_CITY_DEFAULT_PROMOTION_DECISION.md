# Realistic City Default Promotion Decision

Status: **BLOCKED**
Date: 2026-07-13

## Decision

Keep `CityGenerationConfig.topology_mode="standard"` as the runtime default.
Do not create the planned feature commit
`feat(city): promote realistic generator default`.

The explicit `realistic_synthetic_v1` path remains available for diagnostics
and generator development. It does not fall back to legacy when explicitly
selected.

## Evidence

| Gate | Result | Authority |
|---|:---:|---|
| PR62 morphology/plausibility | FAIL | `realistic-city-pr62-plausibility.json` |
| PR63 100k generation wall | FAIL | `realistic-city-pr63-scale.json` |
| PR63 generation peak RSS | PASS | `realistic-city-pr63-scale.json` |
| PR63 realized 100k population | FAIL | `realistic-city-pr63-scale.json` |
| PR63 fixed 20-tick latency | PASS | `realistic-city-pr63-scale.json` |
| PR63 paired-budget throughput | FAIL | `realistic-city-pr63-scale.json` |
| PR63 Rust generation probe | CLOSED | `realistic-city-pr63-scale.json` |

Source fingerprints:

- PR62: `6ab9f8c9c62f36aeedffd67707f2c3e9072274ca91f1e836dc14d69fcde3316b`
- PR63: `149571c18552e5cc655a0c33844fe487a7b6165cea808b1c55a3b47655f5278e`

The machine-readable decision is
`artifacts/runtime_spine_review/realistic-city-pr64-default-promotion-decision.json`.

## Review

Question: Do partial RSS and fixed-latency passes permit default promotion?

Evidence: PR62 fails all 30 maps. PR63 fails generation, actual population,
and paired throughput on every 100k seed.

Inference: The gate is conjunctive. Partial performance success cannot offset
morphology or product-scale failures.

Counterevidence checked: deterministic topology/CSR compilation, no-repair
connectivity, 512 sampled OD reachability, passing RSS ratios, passing fixed
20-tick latency ratios, and explicit spatial-queue substrate.

Decision: keep the default unchanged and close PR64 as `BLOCKED`.

Falsifier: a revised generator passes every unchanged PR62 and PR63 gate with
valid source fingerprints.

Next action: open a new generator specification focused on continuous
non-triangular local fabric, road hierarchy, terrain response, and block/home
capacity sufficient to realize the requested population. Rerun PR62 before
reopening performance or backend work.

## Claim Boundary

This closure is an engineering decision, not an empirical city or traffic
validation result. Diagnostic PNG/HTML artifacts remain smoke evidence only.
