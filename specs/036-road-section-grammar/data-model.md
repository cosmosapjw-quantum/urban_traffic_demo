# Data Model: Road Section Grammar

- `RoadDesignStandard`: explicit widths and maximum lateral shift.
- `RoadSectionUnit`: role, width in meters, optional travel direction.
- `RoadSectionEnd`: ordered unit sequence and derived dimensions.
- `RoadSectionProfile`: start/end sections, interface type, offsets,
  deterministic fingerprint.
