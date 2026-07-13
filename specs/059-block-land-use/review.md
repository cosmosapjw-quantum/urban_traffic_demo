# PR59 Review Record

Status: approved
Date: 2026-07-13

## /review-spec

All blocks receive a typed assignment. `open_space` is an explicit optional
type for non-buildable terrain; the four functional types remain mandatory.
Capacities use named square-meter and per-hectare surfaces, and PR60 retains
ownership of legacy `Zone`/`POI` conversion.

## /review-code

Finding: the first immutable records could accept a false centroid, arbitrary
capacity values, or POI coordinates/capacity inconsistent with their block.

Fix: records now reconstruct and validate block geometry, recompute the
area-based capacity formula, require exact land-use-specific POI mixes, and
bind every POI coordinate, access node, and capacity to its block. No findings
remain.

## /review-drift

Question: Does land use arise from accepted blocks and terrain, or merely
relabel the legacy centroid placement?

Evidence: 24 required maps assign every PR58 block from PR55 terrain and urban
form plus PR56-57 road hierarchy. Seed-29 type shares remain diversified across
all six styles, industrial-residential shared edges are zero, and all
residential blocks have home and leisure access.

Inference: this is a block-authoritative static land-use input, not a wrapper
around legacy nearest-centroid zoning. It does not establish empirical land-use
validity or trip realism.

Counterevidence checked: type collapse, non-buildable assignment, false source
fingerprints, false geometry, arbitrary capacities, duplicate/missing POIs,
industrial adjacency, optional accelerator imports, and legacy regression.

Decision: approve PR59 and move to runtime map compilation. Do not add demand
or runtime mutation to the land-use module.

Falsifier: unassigned blocks, POIs without frontage access, residential and
industrial shared boundaries, or capacities without explicit area units.

Next action: PR60 compiles these immutable blocks and POIs into existing
topology/zoning/CSR/replay/static-render surfaces behind an explicit mode.

## Gates

- targeted: `27 passed in 67.72s`
- full repository: `718 passed in 364.72s`
- Ruff and diff check: passed
