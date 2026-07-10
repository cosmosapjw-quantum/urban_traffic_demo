# Data Model: Typed Road Geometry

- `RoadCenterline`: ID, points in meters, source, source reference, layer,
  optional corridor ID, derived length and fingerprint.
- `LinkGeometryAssignment`: link ID, geometry ID, reverse flag, lateral offset
  in meters.
- `RoadGeometryCatalog`: unique centerlines and assignments, lookup indexes,
  deterministic catalog fingerprint.
