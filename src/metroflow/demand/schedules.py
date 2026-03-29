from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleTemplate:
    name: str
    morning_peak_start_min: int = 420
    morning_peak_end_min: int = 540
    midday_peak_start_min: int = 690
    midday_peak_end_min: int = 780
    evening_peak_start_min: int = 1020
    evening_peak_end_min: int = 1140
    weekday_base_multiplier: float = 1.0
    weekend_base_multiplier: float = 0.8
    weekday_morning_peak_multiplier: float = 1.7
    weekday_midday_peak_multiplier: float = 1.15
    weekday_evening_peak_multiplier: float = 1.55
    weekend_midday_peak_multiplier: float = 1.3
    weekend_evening_peak_multiplier: float = 1.1


def _in_window(minute_of_day: int, start: int, end: int) -> bool:
    return start <= minute_of_day < end


def demand_multiplier(template: ScheduleTemplate, day_type: str, minute_of_day: int) -> float:
    if not 0 <= minute_of_day < 24 * 60:
        raise ValueError("minute_of_day must be within [0, 1440).")
    if day_type not in {"weekday", "weekend"}:
        raise ValueError("day_type must be 'weekday' or 'weekend'.")

    if day_type == "weekday":
        multiplier = template.weekday_base_multiplier
        if _in_window(minute_of_day, template.morning_peak_start_min, template.morning_peak_end_min):
            multiplier = template.weekday_morning_peak_multiplier
        elif _in_window(minute_of_day, template.midday_peak_start_min, template.midday_peak_end_min):
            multiplier = template.weekday_midday_peak_multiplier
        elif _in_window(minute_of_day, template.evening_peak_start_min, template.evening_peak_end_min):
            multiplier = template.weekday_evening_peak_multiplier
        return multiplier

    multiplier = template.weekend_base_multiplier
    if _in_window(minute_of_day, template.midday_peak_start_min, template.midday_peak_end_min):
        multiplier = template.weekend_midday_peak_multiplier
    elif _in_window(minute_of_day, template.evening_peak_start_min, template.evening_peak_end_min):
        multiplier = template.weekend_evening_peak_multiplier
    return multiplier
