# Source Boundary Contract

Input: a proposed city-map implementation diff.

Accepted only when:

- no CSUR package or donor-folder import is added;
- no upstream source file is copied or vendored;
- all behavior is defined by Metroflow contracts and targeted tests;
- claims distinguish road-section generation from city-layout generation.

Failure: reject the diff and require an explicit licensing decision.

Machine-readable authority: `docs/map/city_map_source_policy.json`.
