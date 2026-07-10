# PR36 Review Record

## Review Loop 1

- Found underspecified directional continuity, coercive numeric conversion,
  and ambiguous fingerprint meaning.
- Added exact directional deltas, strict integer/bool handling, and separate
  structural and identity fingerprints.

## Review Loop 2

- Found positional continuity holes for roadside units, unchanged lanes, and
  channels, plus remaining coercive real-number inputs.
- Replaced aggregate comparisons with ordered one-lane and adjacent
  lane+channel edit validation; restricted dimensions and offsets to real
  non-boolean values and normalized overflow.

## Review Loop 3

- Result: approved.

## Validation

- Focused review suite: `25 passed`.
- Combined grammar/geometry/provenance suite: `34 passed`.
- Full repository: `388 passed`.
- Ruff and `git diff --check`: passed.
- Review subagents: closed; zero intentionally open.

## Numerical Impact

Static widths, center offsets, and section fingerprints are introduced. No
link capacity, vehicle stock, routing cost, scheduler, or replay value uses
these profiles in PR36. Road sections remain static contracts only.
