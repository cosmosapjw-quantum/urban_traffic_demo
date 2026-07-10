# Implementation Plan: Typed Road Geometry Contract

- Add immutable geometry entities under `metroflow.map`.
- Validate explicit meter units, finite coordinates, unique identifiers, and
  assignment references.
- Build deterministic endpoint adapter by sorting nodes, links, and undirected
  physical-link groups.
- Export the contract without importing optional accelerators.
- Test contracts before integrating with `PreviewCityTopology` in PR35.

Constitution: contract-first, deterministic, no dynamics/time/cache mutation,
small reversible patch, docs/tests synchronized.
