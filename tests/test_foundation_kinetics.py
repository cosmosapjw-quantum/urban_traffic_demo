import math
from dataclasses import replace
import pytest
from metroflow.foundation_kinetics import (
    VehicleClass,
    PhaseBin,
    characteristic,
    evolve,
    moments,
    passage,
    mean_passage,
)


def test_actual_speed_is_continuous_and_acceleration_is_bounded():
    c = VehicleClass()
    x, v = characteristic(c, 0.0, 10.0, 1.0)
    assert v == pytest.approx(2.0) and x == pytest.approx(1.0)
    for t in (0.0, 0.1, 1.0, 5.0):
        x, v = characteristic(c, 0.0, 10.0, t)
        assert 0 <= v <= min(10.0, 2 * t) + 1e-12


def test_unsaturated_solution_is_exact_characteristic_not_instant_target():
    c = VehicleClass(response_s=5.0)
    x, v = characteristic(c, 2.0, 8.0, 2.0)
    assert v == pytest.approx(8.0 - 6.0 * math.exp(-0.4))
    assert x == pytest.approx(16.0 - 30.0 * (1 - math.exp(-0.4)))
    t, vend = passage(c, 2.0, 8.0, 100.0)
    assert characteristic(c, 2.0, 8.0, t)[0] == pytest.approx(100.0, abs=1e-9)


def test_same_mean_gap_different_correlations_remain_distinguishable():
    c = VehicleClass()
    a = (PhaseBin(100.0, 20.0, 2.0),)
    b = (PhaseBin(50.0, 5.0, 2.0), PhaseBin(50.0, 35.0, 2.0))
    ma = moments(evolve(c, a, 1.0, 20.0))
    mb = moments(evolve(c, b, 1.0, 20.0))
    assert ma[0] == mb[0] == 100.0
    assert ma[1] != pytest.approx(mb[1]) and mb[2] > 0
    scaled = tuple(replace(x, mass=x.mass * 1000) for x in b)
    out = evolve(c, scaled, 1.0, 20.0)
    assert len(out) == 2 and moments(out)[0] == 100000.0
    assert moments(out)[1:] == pytest.approx(mb[1:])


def test_mean_first_passage_not_inverse_mean_speed():
    c = VehicleClass()
    bins = (PhaseBin(0.5, 7.0, 5.0), PhaseBin(0.5, 17.0, 15.0))
    assert mean_passage(c, bins, 20.0, 100.0) == pytest.approx(40 / 3)
    assert 100 / moments(bins)[1] == 10.0


def test_stopping_target_has_finite_coast_distance_not_teleport_stop():
    c = VehicleClass(response_s=2.0, brake_mps2=3.0)
    assert math.isfinite(passage(c, 10.0, 0.0, 10.0)[0])
    assert math.isinf(passage(c, 10.0, 0.0, 23.0)[0])
    assert passage(c, 0.0, 0.0, 0.0) == (0.0, 0.0)


def test_characteristic_semigroup_and_type_specific_response():
    car = VehicleClass()
    truck = VehicleClass("truck", 15.0, 4.0, 0.7, 2.0, 3.0, 1.5, 12.0)
    for v0, u, t, s in ((0.0, 20.0, 3.0, 7.0), (20.0, 0.0, 2.0, 8.0), (5.0, 7.0, 0.3, 4.0)):
        x, v = characteristic(car, v0, u, t)
        y, w = characteristic(car, v, u, s)
        total, end = characteristic(car, v0, u, t + s)
        assert (x + y, w) == pytest.approx((total, end), abs=1e-10)
    assert characteristic(car, 0.0, 10.0, 1.0)[1] > characteristic(truck, 0.0, 10.0, 1.0)[1]


def test_invalid_inputs_and_explicit_vacuum_convention():
    with pytest.raises(ValueError):
        VehicleClass(response_s=0.0)
    with pytest.raises(ValueError):
        PhaseBin(-1.0, 3.0, 1.0)
    with pytest.raises(ValueError):
        characteristic(VehicleClass(), 1.0, 2.0, math.nan)
    assert moments(()) == (0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        mean_passage(VehicleClass(), (), 10.0, 10.0)
