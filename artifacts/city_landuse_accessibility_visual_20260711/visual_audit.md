# Morphology Land-Use Visual Audit

Status: diagnostic only

Reviewed pair: `polycentric_tod`, seed 17, population target 20,000.

## Observations

- Legacy and morphology-gated maps use identical typed roads and differ only in
  zone/POI placement.
- Legacy placement follows coordinate-stride centers; several zone and POI
  overlays accumulate around the central and lower corridor groups.
- Morphology-gated placement moves zone centers to distinct district/subcenter
  anchors and distributes POI clouds across those road fabrics.
- All 18 style/seed runs retain `1.0` POI access validity and `1.0` directed
  representative-zone reachability. Zone/POI IDs, types, and capacities remain
  unchanged.
- The change is intentionally substantial: every run changes all zone centers,
  and at least 99.7% of POI access nodes change.

## Adversarial Limits

- Zone circles are centers, not land-parcel boundaries. The images cannot show
  zoning contiguity, developable area, or parcel-level land-use plausibility.
- Dense POI dots establish access-node distribution, not realistic establishment
  density or observed trip demand.
- Full directed reachability is necessary but weak evidence because the accepted
  generated networks are already strongly connected.
- These PNGs and HTML maps are smoke diagnostics, not city-replication or demand
  validation evidence.

## Decision

PR45 does not find an accessibility blocker in the reviewed placement, but this
diagnostic does not authorize PR46 or a new demand-coupling policy. Any PR46
decision requires separate demand-defect evidence. Zone spatial support or
parcel/block coverage remains an independent land-use question.
