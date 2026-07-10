# Implementation Plan: City Map Source Provenance Boundary

**Branch**: `008-routing-runtime-integration` | **Date**: 2026-07-10

## Summary

Add an authoritative source-provenance document, a bounded PR roadmap, and a
targeted contract test. No runtime or dependency changes are permitted.

## Technical Context

- Language: documentation plus Python 3.12 test
- Dependencies: standard library only
- Testing: pytest and ruff
- Runtime impact: none

## Constitution Check

- Contract impact: documentation authority only.
- Time-scale impact: none.
- Cache invalidation impact: none.
- Replay impact: none.
- Benchmark impact: none.
- Small reversible patch: yes.

## Files

- `docs/map/CITY_MAP_SOURCE_PROVENANCE.md`
- `docs/map/city_map_source_policy.json`
- `docs/harness/CITY_MAP_PR_LIST.md`
- `docs/CITY_GENERATION_DESIGN.md`
- `docs/PRD.md`
- `docs/RESEARCH_SYNTHESIS.md`
- `docs/harness/DECISION_LOG.md`
- `specs/001-metroflow/research.md`
- `specs/033-city-map-provenance-boundary/`
- `tests/test_city_map_provenance.py`

Existing `docs/harness/VALIDATION_LEDGER.md` and
`artifacts/static_city_map_review_20260710/` changes predate PR33 and are
explicitly excluded from staging.
