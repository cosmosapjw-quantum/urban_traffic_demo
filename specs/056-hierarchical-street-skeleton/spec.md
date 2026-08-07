# Feature Specification: Hierarchical Street Skeleton

Status: implementation

## Goal

Convert accepted terrain and urban-form fields into a deterministic connected
physical arterial/expressway/bridge skeleton without connectivity repair.

## Requirements

- Connect every center and boundary gateway with a deterministic MST plus a
  bounded set of redundancy edges.
- Route each edge through buildable terrain using slope, development, and water
  costs on the bounded raster.
- Split water-crossing edge runs into explicit bridge streets and keep all
  physical units explicit.
- Preserve complete provenance and deterministic fingerprints.
- Fail closed on mismatched field fingerprints or unreachable anchors.

## Non-goals

- No local streets, planar block extraction, zones, runtime mode, or backend.
- No connectivity repair, external data, or empirical road calibration.

## Acceptance

- All anchors are connected by construction and at least one cycle edge exists.
- River-constrained fixtures contain explicit bridge and non-bridge streets.
- All six styles repeat exact fingerprints and remain inside terrain bounds.
- Legacy generator and runtime behavior remain unchanged.
