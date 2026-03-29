from dataclasses import dataclass


@dataclass(frozen=True)
class UnitsConfig:
    time_unit_seconds: float = 1.0
    length_unit_meters: float = 1.0
    speed_unit_m_per_s: float = 1.0
    flow_unit_veh_per_s: float = 1.0


def validate_units_config(units: UnitsConfig) -> None:
    if units.time_unit_seconds <= 0.0:
        raise ValueError("time_unit_seconds must be positive.")
    if units.length_unit_meters <= 0.0:
        raise ValueError("length_unit_meters must be positive.")
    if units.speed_unit_m_per_s <= 0.0:
        raise ValueError("speed_unit_m_per_s must be positive.")
    if units.flow_unit_veh_per_s <= 0.0:
        raise ValueError("flow_unit_veh_per_s must be positive.")
