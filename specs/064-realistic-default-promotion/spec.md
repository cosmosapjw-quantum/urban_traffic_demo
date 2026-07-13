# Feature Specification: Realistic City Default Promotion Decision

Status: blocked by canonical PR62 and PR63 evidence

## Goal

Consume the frozen plausibility and scale artifacts and either promote
`realistic_synthetic_v1` or record a fail-closed decision without changing the
runtime default.

## Requirements

- Validate PR62 and PR63 source fingerprints through their authoritative
  loaders.
- Require every plausibility, generation, realized-population, latency, RSS,
  and paired-throughput gate to pass before promotion.
- Require the current default to be `standard` before any admitted migration.
- When any gate fails, preserve `standard`, record `BLOCKED`, and add no
  generator/runtime feature code or fallback.
- Keep diagnostic images and host timings outside empirical validation claims.

## Canonical Decision

PR62 passes `0/30` maps. PR63 fails generation, realized population, and
paired throughput on all three 100k seeds. Promotion is therefore blocked and
the planned feature commit `feat(city): promote realistic generator default`
is forbidden.

## Reopening Conditions

A future spec may reopen promotion only after a revised generator reruns the
unchanged PR62 and PR63 matrices and every conjunctive gate passes. Threshold
tuning, renderer-only changes, connectivity repair, or performance-only
improvement cannot reopen this decision.
