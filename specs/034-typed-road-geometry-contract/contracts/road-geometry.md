# Road Geometry Contract

Inputs are finite two-dimensional meter coordinates and stable integer IDs.
Outputs are immutable centerline and assignment records. Catalog construction
rejects duplicate IDs, unresolved references, and invalid offsets. Endpoint
adaptation is deterministic and does not mutate topology objects.
