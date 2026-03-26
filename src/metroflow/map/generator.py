from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticCityConfig:
    num_zones: int = 64
    include_bridge_bottleneck: bool = True
    include_ring_radial: bool = True
