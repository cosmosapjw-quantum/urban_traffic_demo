from dataclasses import dataclass

from metroflow.demand.schedules import ScheduleTemplate, demand_multiplier


@dataclass(frozen=True)
class TripRequest:
    origin_zone: int
    destination_zone: int
    departure_minute: int
    purpose: str


def scheduled_trip_count(
    population: int,
    base_rate_per_tick: float,
    day_type: str,
    minute_of_day: int,
    template: ScheduleTemplate,
) -> int:
    if population < 0:
        raise ValueError("population must be non-negative.")
    if base_rate_per_tick < 0.0:
        raise ValueError("base_rate_per_tick must be non-negative.")
    multiplier = demand_multiplier(template, day_type=day_type, minute_of_day=minute_of_day)
    return int(round(population * base_rate_per_tick * multiplier))
