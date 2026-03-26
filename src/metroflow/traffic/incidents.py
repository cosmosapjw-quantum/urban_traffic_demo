from dataclasses import dataclass


@dataclass(frozen=True)
class Incident:
    edge_id: int
    capacity_multiplier: float
    duration_steps: int
