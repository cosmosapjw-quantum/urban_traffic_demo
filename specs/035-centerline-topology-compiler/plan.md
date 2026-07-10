# Implementation Plan: Centerline Topology Compiler

1. Extend static `RoadLink` metadata with a physical road identity.
2. Assign the same identity in bidirectional generator and repair builders.
3. Finalize all generated topologies through connectivity repair, topology
   validation, and endpoint geometry catalog construction.
4. Add explicit `CityGenerationConfig.topology_mode` propagation.
5. Include geometry fingerprint in static UI cache version and state metadata.
6. Rename legacy hierarchy diagnostic keys and document artifact migration.

No runtime traffic arrays or optional backend imports are changed.
