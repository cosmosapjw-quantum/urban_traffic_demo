from metroflow.demand.schedules import ScheduleTemplate, demand_multiplier
from metroflow.demand.trip_generation import scheduled_trip_count


def test_weekday_and_weekend_profiles_differ():
    template = ScheduleTemplate(name="baseline")

    weekday_peak = demand_multiplier(template, "weekday", 450)
    weekend_peak = demand_multiplier(template, "weekend", 450)

    assert weekday_peak != weekend_peak


def test_time_of_day_has_multiple_distinct_peaks():
    template = ScheduleTemplate(name="baseline")

    morning = demand_multiplier(template, "weekday", 450)
    midday = demand_multiplier(template, "weekday", 720)
    evening = demand_multiplier(template, "weekday", 1050)

    assert len({morning, midday, evening}) >= 2
    assert morning > demand_multiplier(template, "weekday", 120)
    assert evening > demand_multiplier(template, "weekday", 120)


def test_scheduled_trip_count_is_deterministic():
    template = ScheduleTemplate(name="baseline")

    count_a = scheduled_trip_count(100_000, 0.001, "weekday", 450, template)
    count_b = scheduled_trip_count(100_000, 0.001, "weekday", 450, template)

    assert count_a == count_b
