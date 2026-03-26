from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleTemplate:
    name: str
    morning_peak_start_min: int = 420
    morning_peak_end_min: int = 540
    evening_peak_start_min: int = 1020
    evening_peak_end_min: int = 1140
