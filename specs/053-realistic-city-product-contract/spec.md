# Feature Specification: Realistic Synthetic City Product Contract

Status: implementation

## Goal

Freeze the product, public contract, measurable quality thresholds, claim
boundary, and ordered implementation queue for a realistic synthetic 2D city
that compiles into the existing deterministic traffic runtime.

## Requirements

- Preserve Python 3.12 and NumPy as runtime authority.
- Preserve `standard` as the default until a separate promotion PR passes.
- Add no runtime behavior, dependency, backend, or external data in PR53.
- Freeze the accepted planar sidecar as the negative visual/structural control.
- Define fixed topology, geometry, block, accessibility, and scale thresholds.
- Define the explicit `realistic_synthetic_v1` and `block_based_v1` contracts
  for later implementation PRs without accepting them in runtime config yet.
- Keep real-city values comparison-only and preserve the prohibition on
  external-data learning and named-city replication.

## Acceptance

- Product PRD and city PR list agree on PR53-PR64 order and promotion policy.
- Thresholds are numeric or mechanically derived and cannot be tuned by later
  implementation PRs without a new decision record.
- No source, dependency, test expectation, or runtime default changes.
- Review record closes spec, documentation-quality, and drift checks.

## Compact CCoT

Question: What must change for a generated map to be a realistic synthetic
simulation input rather than a richer schematic renderer?

Evidence: Current planar, morphology, and accessibility gates pass, while the
canonical contact sheet retains precinct islands, exposed skeleton corridors,
and no block or terrain authority.

Inference: The next lane needs a typed terrain-to-block generation contract and
simulation-input promotion gates, not another renderer or raster counter.

Counterevidence checked: Existing topology, section, turn, OD, and replay
contracts are reusable and should not be replaced.

Decision: Freeze a new explicit mode and PR53-PR64 sequence while retaining the
legacy default and claim ceiling.

Falsifier: The new mode cannot pass topology/block gates within the fixed
runtime budget without weakening replay or restoring repair-link masking.

Next action: PR54 extracts compatibility and stage boundaries before new
generation behavior is implemented.
