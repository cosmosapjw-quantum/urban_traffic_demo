from dataclasses import dataclass


@dataclass(frozen=True)
class CitizenRecord:
    citizen_id: int
    home_zone: int
    work_zone: int
    archetype: str
