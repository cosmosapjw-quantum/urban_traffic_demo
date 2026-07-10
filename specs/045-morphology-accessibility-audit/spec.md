# Feature Specification: Morphology Accessibility Audit

Status: accepted (`499 passed`; Ruff and diff checks clean)

## Goal

Determine whether morphology-gated zone/POI placement preserves access-node and
directed inter-zone reachability before any demand-policy change is considered.

## Scope

- Add reusable deterministic directed-pair reachability analysis without route
  scoring or backend dispatch.
- Audit zone-node coverage, POI access validity, directed representative-zone
  reachability, POI dispersion, and legacy/morphology placement separation.
- Run at least three unique seeds and render one legacy/morphology static-map
  pair per style through the existing typed geometry renderer.
- Write JSON, Markdown, HTML index, per-map HTML, and manifest artifacts.
- Preserve diagnostic-only claim language and coupling provenance.

## Non-goals

- Demand generation, route legality, runtime defaults, topology generation, or
  backend changes.
- External data, named-city fit, learned land use, or empirical validation.
- A new renderer or duplicate shortest-path implementation.

## Acceptance

- Equivalent ordered node-pair inputs produce deterministic reachability.
- Missing POI nodes and zone mismatches reduce access validity fail-closed.
- Generated legacy and admitted morphology placements both retain full access
  and directed zone-pair reachability across the audit matrix.
- Morphology mode differs from legacy in zone centers and/or POI anchors.
- Static map payloads expose requested/resolved coupling and placement
  fingerprint metadata.
- Audit artifacts explicitly remain diagnostic and do not authorize PR46.

## Review Closure

- `/review-spec`: closed unverified renderer provenance by recomputing the
  effective zoning fingerprint before publishing coupling metadata.
- `/review-code`: closed duplicate-ID collapse, unbounded zero-baseline
  retention, unsafe style paths, and stale output-directory findings.
- `/review-drift`: downscoped the result from PR46 rejection to explicit
  non-authorization and retained visual outputs as diagnostics only.

## Compact CCoT

Question: Does morphology-aware placement preserve network accessibility?
Evidence: PR44 changed static placement behind recomputed morphology evidence.
Inference: Measure access/reachability before changing downstream demand.
Counterevidence checked: Weak connectivity alone does not prove directed OD reachability.
Decision: Add a bounded diagnostic audit and reuse existing rendering.
Falsifier: Any generated run loses POI validity or directed zone-pair reachability.
Next action: Require separate decision-changing demand-defect evidence before
any PR46 admission; visual preference and this audit are insufficient.
