# PR41 Review

## /review-spec

Result: pass

- Scope stays in synthetic city morphology, metrics, metadata, tests, and
  diagnostic rendering.
- No runtime network fetch, raw OSM extract, external-data learning, or backend
  dependency was added.
- `auto` preserves scenario-resolved defaults; explicit styles remain opt-in.
- Real-city observations are marked reference-only, not calibration or city
  replication evidence.

## /review-code

Fix loop 1 findings:

1. `river_constrained` selected bridge candidates from longitudinal roads,
   reversing the barrier-crossing meaning.
2. Cell-scale grid calculations remained after district-scale fabric replaced
   them, obscuring the active implementation.

Fixes:

- Added river-specific transverse crossing selection and a regression test that
  bridge links are transverse.
- Removed dead calculations.
- Hardened planar intersection tests to use parametric interior positions and
  deterministic same-coordinate endpoint aliases.

Fix loop 2 result: no open correctness finding. Focused tests and full suite
initially exposed an unsupported `standard` + new-style combination that could
mislabel a radial backbone. The combination now fails closed in config and the
direct generator API. Focused tests and full suite pass after the fix. The
implementation is large but remains within one bounded city-map slice;
reference data, metric computation, atlas rendering, and generation orchestration
have separate module ownership.

## /review-drift

Question: Did this PR improve structural diversity or only add preset labels?

Evidence: At seed 17, orientation-order spans `0.103–0.853` and dead-end share
spans `0.022–0.323`; all six geometry fingerprints differ and all explicit
planar forms pass the city-map contract.

Inference: The forms are materially distinct under common metrics.

Counterevidence checked: visual review still shows sparse district coverage,
long connectors, excessive four-way share in polycentric/mixed styles, and
excess dead ends in the corridor style.

Decision: Close PR41 as diversity substrate only. Do not claim named-city
replication or general urban realism.

Falsifier: Multi-seed block/density distributions collapse across styles or
remain outside broad empirical envelopes.

Next action: PR42 block continuity, density envelope, connector/local length,
and intersection-mix gates.

## Gates

- morphology/planar/closure targeted: `21 passed`
- init/replay/static compatibility targeted: `39 passed`
- final full suite: `439 passed in 68.95s`
- Ruff: passed
- `git diff --check`: passed
