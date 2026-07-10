# Research: Centerline Topology Integration

The current standard generator already repairs connectivity. The local-fabric
sidecar does not, so a shared finalization boundary is required before either
can enter initialization. Physical road IDs are needed because endpoint/class
tuples contain legitimate parallel pairs and cannot infer pairing safely.
