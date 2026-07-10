# City Map Source Provenance Boundary Spec

## Goal

Define which externally researched road-generation concepts Metroflow may
reimplement and prevent accidental GPL source ingestion or false claims about
city-layout capabilities.

## User Scenarios

### US1 - Implement From A Safe Internal Contract (P1)

An implementer can read one Metroflow-owned source-boundary document and know
which concepts are permitted, which source surfaces are excluded, and when work
must stop for a licensing decision.

### US2 - Review City-Map Claims (P2)

A reviewer can distinguish implemented Metroflow behavior from proposed
CSUR-inspired section work and reject claims that CSUR generates complete city
layouts.

## Functional Requirements

- **FR-001:** The project MUST record the reviewed upstream repository, commit,
  and license.
- **FR-002:** The project MUST list permitted neutral concepts without upstream
  source excerpts.
- **FR-003:** The project MUST prohibit source copying, vendoring, and runtime
  imports until an explicit licensing decision exists.
- **FR-004:** The project MUST separate centerline generation, topology
  compilation, road-section compilation, and node-interface compilation.
- **FR-005:** The roadmap MUST preserve link-level mesoscopic runtime authority.

## Contract Requirements

- **CR-001:** `docs/map/CITY_MAP_SOURCE_PROVENANCE.md` is authoritative for
  external-source use in PR33-PR40.
- **CR-002:** `docs/harness/CITY_MAP_PR_LIST.md` is authoritative for execution
  order and review lifecycle.
- **CR-003:** Violation of the source boundary fails closed before code review.

## Determinism And Replay

This PR changes no runtime state, randomness, scheduling, cache, or replay
contract.

## Success Criteria

- **SC-001:** The source boundary names all five permitted concept groups and
  all six excluded source surfaces.
- **SC-002:** Repository dependency metadata contains no CSUR dependency.
- **SC-003:** Documentation does not describe CSUR as a city-layout generator.

## Validation Plan

- Targeted documentation contract test.
- `pytest -q`, `ruff check .`, and `git diff --check`.
- Review the exact staged files before commit.

## Assumptions

- Metroflow has not adopted GPL-3.0 as a repository distribution license.
- A future licensing decision may replace this boundary in a separate PR.

## Remaining Risks

- Conceptual similarity still needs careful provenance review.
- This engineering boundary is not legal advice.

## Compact CCoT

Question: Can CSUR source be copied to improve the generated map?
Evidence: The reviewed repository is GPL-3.0 and produces road assets rather
than city layouts; Metroflow has no root license declaration.
Inference: Direct copying is an avoidable licensing and architecture risk.
Counterevidence checked: Pure core modules are technically separable from
Blender and Unity, but license obligations remain and they do not solve
centerline layout.
Decision: Reimplement only neutral concepts from an internal behavioral spec.
Falsifier: An explicit project licensing decision authorizes direct GPL reuse.
Next action: Add typed Metroflow-owned road geometry contracts.
