from dataclasses import dataclass


@dataclass(frozen=True)
class TripRequest:
    origin_zone: int
    destination_zone: int
    departure_minute: int
    purpose: str
