# Feature Specification: Planar Block Compiler

Status: complete

## Goal

Compile realistic physical streets into a same-layer planar directed graph and
extract deterministic bounded-face urban blocks with complete road frontage.

## Requirements

- Convert every physical polyline segment to paired directed links with source
  street provenance and explicit units.
- Reuse the accepted endpoint planarizer; no second intersection authority.
- Extract bounded faces with deterministic half-edge traversal.
- Reject remaining proper intersections, tiny blocks below `100m2`, short
  physical-segment share above `2%`, median block area outside
  `3,000-30,000m2`, or p95 above `120,000m2`.
- Every block must retain at least one source street frontage ID.

## Non-goals

- No parcels, land use, zoning, runtime topology mode, renderer, or backend.
- No connectivity repair or threshold tuning by style/seed.

## Acceptance

- All six styles pass planar, segment, block-area, frontage, provenance, and
  deterministic fingerprint gates.
- Existing legacy/sidecar behavior remains unchanged.
