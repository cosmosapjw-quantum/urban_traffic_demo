from dataclasses import dataclass


@dataclass(frozen=True)
class Archetype:
    name: str
    urgency: float = 1.0
    exploration: float = 0.1
    reroute_threshold: float = 0.2
