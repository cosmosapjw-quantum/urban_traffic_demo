# Planar City Map Visual Audit

Label: DIAGNOSTIC ONLY, NOT VALIDATION EVIDENCE.

## Reviewed Artifacts

- `full.png`: physical roads, zones, and POIs.
- `focused.png`: largest-component view; identical extent is expected after repair.
- `roads.png`: physical road ribbons only.
- `zones.png`: zone centroids only.
- `pois.png`: POI points only.
- `manifest.json`: fingerprints, counts, planarization, and sampled-OD metrics.

The HTML sources were generated under `/tmp/metroflow-pr40` and intentionally
were not committed because each standalone payload is 14-17 MB.

## Contract Findings

- Explicit mode: `sidecar_local_fabric_planar`, seed `44`.
- Proper same-layer crossings: `2665` before, `0` after planarization.
- Nodes: `3280`; directed links: `12868`; physical roads: `6434`.
- Weak components: `1`; sampled reachable ODs: `32 / 32`.
- Geometry, section, and node-interface fingerprints are present in the manifest.
- Full and focused images are identical because deterministic connectivity repair
  leaves one component. This is expected, not independent visual evidence.

## Adversarial Visual Findings

1. The output still does not resemble a continuous realistic urban street fabric.
2. Dense star-shaped local clusters are connected by long, sparse, nearly direct
   corridors with large undeveloped gaps.
3. Planarization makes crossings topologically legal but does not improve the
   underlying road-placement morphology; it can add nodes without adding blocks.
4. Several high-capacity corridors converge with weak hierarchy transitions and
   little visible neighborhood-scale mesh between centers.
5. Zones are centroid circles, not polygons, and do not establish land-use coverage.
6. POI clusters expose demand placement but obscure roads in the composite view;
   layer-isolated outputs are required for inspection.

## Admission Decision

The planar mode passes topology/geometry contract checks but remains explicit-only.
A trial default promotion increased the full suite from about `48 s` to about
`281 s` and broke an existing route-ID regression. After reverting the default,
the reviewed full suite passed in about `137 s`, including the intentionally
expensive explicit-planar tests.

The next city-quality slice should redesign local-fabric placement and block
formation, using offline OSM reference metrics for comparison. More renderer
styling or unconditional planarization would not resolve the morphology defect.
