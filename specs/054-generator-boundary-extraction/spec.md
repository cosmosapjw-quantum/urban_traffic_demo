# Feature Specification: Generator Boundary Extraction

Status: implementation

## Goal

Create stable generated-map and topology-finalization boundaries before adding
the realistic generator, without changing any existing generated topology,
runtime default, or import path.

## Requirements

- Move `PreviewCityTopology` into a focused generated-map contract module.
- Move finalization, connectivity repair, planarization, geometry/section/node
  compilation, turn compilation, and quality validation into a focused module.
- Keep `GeneratorV2`, `metroflow.city.PreviewCityTopology`, and all current
  preview modes source-compatible.
- Do not modify the legacy `_build_preview_topology` algorithm.
- Freeze exact node/link counts and geometry/turn fingerprints for standard,
  sidecar, and planar seed-17 fixtures.
- Core imports must not load JAX, torch, CUDA, or `_metroflow_rust`.

## Non-goals

- No realistic mode, terrain field, block model, zoning change, backend, or
  dependency is implemented in PR54.
- No generic stage registry, ECS, plugin framework, or legacy cleanup.

## Acceptance

- Existing and new targeted city tests pass.
- All three frozen fingerprints remain exact.
- The legacy builder no longer owns generated-map contracts or finalization.
- Full repository, Ruff, and diff gates pass.
