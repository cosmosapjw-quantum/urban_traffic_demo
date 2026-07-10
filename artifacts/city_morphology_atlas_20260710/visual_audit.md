# City Morphology Atlas Visual Audit

Status: diagnostic, not validation

Seed: 17

Topology mode: `sidecar_local_fabric_planar`

## Observations

- `ring_radial` remains the legacy control and visibly concentrates long links
  through a central region.
- `grid_core` has one dominant orthogonal orientation and continuous trunk
  lines, but its district fabrics still read as separated patches.
- `polycentric_tod` avoids mandatory downtown traversal and exposes several
  comparable centers, but the inter-center skeleton remains sparse.
- `river_constrained` has longitudinal banks and exactly three transverse
  bridge groups. Its disconnected-looking local branches are graph-connected,
  but the dead-end share remains too high.
- `superblock_mixed` shows competing local grid orientations and is the most
  visibly heterogeneous planned form. Long connectors remain overemphasized.
- `organic` removes the global radial shell and adds district loops, but several
  limbs remain too tree-like for a dense established city.

## Adversarial conclusion

PR41 fixes morphology collapse: the generator can now produce materially
different macro structures under one typed topology contract. It does not close
the realism problem. The next acceptance gate must measure occupied-area street
density, block continuity, connector/local length ratios, intersection-type
mixtures, and multi-seed distribution stability. Renderer refinements alone
cannot resolve these defects.
