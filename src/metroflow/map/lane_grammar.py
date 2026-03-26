from dataclasses import dataclass
from enum import Enum


class SegmentInterfaceType(str, Enum):
    BASE = "base"
    SHIFT = "shift"
    TRANSITION = "transition"
    RAMP = "ramp"


@dataclass(frozen=True)
class CarriagewayProfile:
    lane_count_forward: int
    lane_count_backward: int
    median: bool = False
    roadside_profile: str = "urban"
