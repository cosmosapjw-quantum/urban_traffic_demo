from dataclasses import dataclass


@dataclass(frozen=True)
class UnitsConfig:
    time_unit_seconds: float = 1.0
    length_unit_meters: float = 1.0
    speed_unit_m_per_s: float = 1.0
    flow_unit_veh_per_s: float = 1.0
