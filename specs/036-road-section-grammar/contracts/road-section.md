# Road Section Contract

The grammar describes static cross-sections only. All dimensions are meters.
Construction raises `ValueError` for non-finite widths/offsets, invalid travel
directions, empty lane surfaces, or interface-specific invariant violations.
