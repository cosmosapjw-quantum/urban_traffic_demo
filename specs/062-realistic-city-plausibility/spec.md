# Feature Specification: Realistic City Plausibility Audit

Status: complete; canonical product gate failed closed

## Goal

Audit six realistic synthetic morphology styles across five fixed seeds against
the pinned street-network reference corpus and PR53 structural thresholds,
without tuning generation or promoting diagnostic images to validation.

## Requirements

- Fix the canonical matrix to all six registered styles and seeds
  `17, 29, 41, 44, 53`.
- Derive each empirical metric envelope mechanically from the minimum and
  maximum pinned corpus values, expanded by 20 percent.
- Evaluate orientation order/entropy, median physical segment length,
  circuity, mean node degree, dead-end share, and four-way share.
- Preserve PR53 topology, compiler, access, segment, block, frontage, and
  land-use gates for every map.
- Record hierarchy shares, orientation concentration, repeated-length share,
  block-area repetition, land-use mix, terrain water/buildable shares, and
  center count as diagnostic-only counterevidence.
- Write JSON, Markdown, HTML contact sheet, and manifest artifacts with explicit
  claim status and source provenance.
- Keep raw OSM data, network access, named-city fitting, external-data learning,
  and runtime default changes out of scope.

## Acceptance

- Schema/envelope/rendering/import-firewall tests pass.
- The canonical 30-map audit runs without generation failure and records every
  style/seed exactly once.
- Overall plausibility passes only if every map meets every fixed empirical and
  structural gate. Failure is evidence and must not trigger threshold tuning.
- Contact-sheet layers are diagnostic only: terrain, roads, blocks, land use,
  and compiled runtime topology.

## Claim Boundary

An accepted audit supports only a broad synthetic street/block distribution
claim. It does not validate a named city, traffic dynamics, route choice,
demand, land-use evolution, or visual realism. A failed audit blocks default
promotion but does not invalidate the deterministic simulation-input substrate.
