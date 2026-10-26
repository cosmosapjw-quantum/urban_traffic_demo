"""T02 analytic characteristics, mixture limits and closure counterexamples."""

import math
from dataclasses import replace
import pytest
from metroflow.foundation_kinetics import VehicleClass, PhaseBin, evolve, moments, characteristic
from metroflow.gap_transport import PairBin, LeaderReport, control
from metroflow.v1.city import CityContractError
from metroflow.v1.kinetics import (
    ClassMass,
    KineticEnvironment,
    compile_bulk,
    coefficients,
    advance_bulk,
    predict_passage,
    latent_reference,
    pair_compatibility,
)


def constant(p=1.0, speed=2.0):
    c = VehicleClass(response_s=5.0)
    return compile_bulk((ClassMass(c, 10, p, 0.0, 0.0),), speed_mps=speed), KineticEnvironment(
        1000.0, 8.0, 0.0
    )


def test_frozen_target_exact_distance_and_continuous_speed():
    s, e = constant()
    r = advance_bulk(s, e, 2.0)
    assert r.state.speed_mps == pytest.approx(8.0 - 6.0 * math.exp(-0.4))
    assert r.distance_m == pytest.approx(16.0 - 30.0 * (1 - math.exp(-0.4)))
    a = advance_bulk(s, e, 0.7)
    b = advance_bulk(a.state, e, 1.3)
    assert a.distance_m + b.distance_m == pytest.approx(r.distance_m)
    assert b.state.speed_mps == pytest.approx(r.state.speed_mps, abs=1e-12)
    assert b.state.classes == r.state.classes
    assert s.time_s == 0 and s.speed_mps == 2


def test_passage_cost_is_root_of_same_transport_characteristic():
    s, e = constant()
    prediction = predict_passage(s, e, 100.0)
    assert prediction.status == "PASS"
    assert advance_bulk(s, e, prediction.elapsed_s).distance_m == pytest.approx(100.0, abs=1e-9)
    assert prediction.speed_mps == pytest.approx(
        advance_bulk(s, e, prediction.elapsed_s).state.speed_mps
    )
    assert prediction.elapsed_s > 100 / 8


def test_mixture_response_weights_and_conservative_limits():
    car = VehicleClass("car", 20, 2, 2, 4, 2, 1, 5)
    truck = VehicleClass("freight", 12, 4, 0.5, 2, 3, 1.5, 12)
    s = compile_bulk((ClassMass(car, 3, 1.0, 0, 0), ClassMass(truck, 1, 0.2, 0, 0)), speed_mps=0)
    e = KineticEnvironment(1000, 30, 0)
    c = coefficients(s, e)
    assert c.admissible_mps == 12
    assert c.response_s == pytest.approx(1 / (0.75 / 2 + 0.25 / 4))
    assert c.target_mps == pytest.approx(12 * (0.75 / 2 + 0.25 * 0.2 / 4) / (0.75 / 2 + 0.25 / 4))
    assert c.mean_gap_m == (1000 - 3 * 5 - 12) / 4
    r = advance_bulk(s, e, 1.0)
    assert r.state.speed_mps == pytest.approx(0.5)
    assert r.distance_m == pytest.approx(0.25)
    assert r.state.mass_veh == 4


def test_class_fragmentation_and_mass_scaling_preserve_physics():
    s, e = constant(0.7)
    c = s.classes[0]
    fragmented = compile_bulk(
        (replace(c, mass_veh=4), replace(c, mass_veh=6)), speed_mps=s.speed_mps
    )
    assert fragmented == s
    scaled = compile_bulk((replace(c, mass_veh=1000),), speed_mps=s.speed_mps)
    r = advance_bulk(s, e, 3)
    q = advance_bulk(scaled, replace(e, lane_length_m=100000), 3)
    assert q.distance_m == r.distance_m and q.state.speed_mps == r.state.speed_mps
    assert q.state.classes[0].latent == r.state.classes[0].latent


def test_sudden_stop_has_finite_braking_not_instant_cap_clipping():
    s, e = constant(speed=30)
    e = replace(e, cap_mps=0)
    r = advance_bulk(s, e, 0.1)
    assert r.state.speed_mps == pytest.approx(29.6)
    assert r.distance_m == pytest.approx(2.98)
    assert predict_passage(s, e, 1000).status == "UNREACHABLE"
    assert predict_passage(s, e, 1).status == "PASS"


def test_latent_reference_transient_and_variance_are_not_binary_speed():
    r = latent_reference(20, 0.2, 0.3, 3, 1, 20, 2)
    assert r["mean_mps"] == pytest.approx(17.65390997925689)
    assert r["latent_binary_mean_mps"] == pytest.approx(12.414553294057308)
    assert r["stationary_variance_m2_s2"] == pytest.approx(38.4)
    assert r["binary_variance_m2_s2"] == pytest.approx(96.0)
    # Resonance rate=1/tau uses the finite analytic limit.
    r = latent_reference(20, 0.2, 0.3, 2, 1, 20, 2)
    assert r["mean_mps"] == pytest.approx(8 + 12 * math.exp(-1) * (1 + 1))


def test_finite_response_split_refines_against_independent_exact_mean():
    car = VehicleClass(response_s=3, accel_mps2=100, brake_mps2=100)
    # lane length N*(h+ell)=100 with h=95 makes hazard exactly .3/s.
    s = compile_bulk((ClassMass(car, 1, 1, 0.2, 0.3, 100),), speed_mps=20)
    e = KineticEnvironment(100, 20, 0)
    exact = latent_reference(20, 0.2, 0.3, 3, 1, 20, 2)["mean_mps"]
    errors = []
    for dt in (0.5, 0.25, 0.125):
        current = s
        for _ in range(round(2 / dt)):
            current = advance_bulk(current, e, dt).state
        errors.append(abs(current.speed_mps - exact))
        assert current.classes[0].latent == pytest.approx(0.4 + 0.6 * math.exp(-1))
    assert errors[1] < errors[0] / 3.5 and errors[2] < errors[1] / 3.5


def test_future_observation_rejected_and_same_perceived_inputs_same_motion():
    s, e = constant()
    with pytest.raises(CityContractError, match="future"):
        advance_bulk(s, replace(e, stamp_s=1), 0.1)
    with pytest.raises(CityContractError, match="future"):
        predict_passage(s, replace(e, stamp_s=1), 10)
    # Unobserved physical change cannot enter this surface: only admitted e.
    c = VehicleClass()
    a = PairBin(c, 1, 50, 10, 15)
    b = replace(a, w=1)
    assert control(a, None, 0, 0.1, 20, 4) == control(b, None, 0, 0.1, 20, 4)
    with pytest.raises(ValueError, match="future"):
        control(a, LeaderReport(1, 15), 0, 0.1, 20, 4)


def test_gap_oracle_necessary_marginals_and_nonlinear_hazard_counterexample():
    c = VehicleClass()
    s = compile_bulk((ClassMass(c, 2),), speed_mps=10)
    e = KineticEnvironment(110, 20, 0)
    pairs = (PairBin(c, 1, 30, 10, 10), PairBin(c, 1, 70, 10, 10))
    report = pair_compatibility(s, e, pairs, ("car", "car"))
    assert report["status"] == "PASS_NECESSARY_ONLY"
    assert report["safety"] == "NOT_CERTIFIED"

    def phi(h):
        return 0.3 * (10 / (h + 5)) ** 2

    assert (phi(30) + phi(70)) / 2 > coefficients(s, e).hazards_s_inv[0]
    assert (
        pair_compatibility(s, e, (replace(pairs[0], w=9), pairs[1]), ("car", "car"))["status"]
        == "MODEL_ERROR"
    )
    assert (
        pair_compatibility(s, e, (replace(pairs[0], h=31), pairs[1]), ("car", "car"))["status"]
        == "MODEL_ERROR"
    )
    assert pair_compatibility(s, e, pairs, ("car", "unknown"))["status"] == "MODEL_ERROR"
    # Independent continuous gap quadrature sees a distribution, not uniform gap.
    bins = (PhaseBin(1, 4, 2), PhaseBin(1, 96, 2))
    varied = moments(evolve(c, bins, 1, 20))
    uniform = moments(evolve(c, (PhaseBin(2, 50, 2),), 1, 20))
    assert varied[1] != pytest.approx(uniform[1]) and varied[2] > 0


def test_vacuum_overpacking_horizon_and_budget_are_distinct():
    s, e = constant()
    vacuum = compile_bulk(())
    assert advance_bulk(vacuum, e, 1).distance_m == 0
    assert predict_passage(vacuum, e, 1).status == "UNREACHABLE"
    with pytest.raises(CityContractError) as exc:
        advance_bulk(s, replace(e, lane_length_m=49), 1)
    assert exc.value.status == "PHYSICAL_INFEASIBLE"
    assert predict_passage(s, e, 100, horizon_s=0.1).status == "HORIZON_REACHED"
    with pytest.raises(RuntimeError, match="BLOCKED_RESOURCE") as exc:
        predict_passage(s, e, 10000, max_steps=1)
    assert exc.value.checkpoint.mass_veh == s.mass_veh


def test_positive_mass_and_no_mixing_incompatible_classes():
    c = VehicleClass()
    with pytest.raises(CityContractError):
        ClassMass(c, -1)
    with pytest.raises(CityContractError, match="incompatible"):
        compile_bulk((ClassMass(c, 1), ClassMass(replace(c, response_s=4), 1)))
    with pytest.raises(CityContractError, match="three"):
        compile_bulk(tuple(ClassMass(replace(c, name=str(i)), 1) for i in range(4)))


def test_time_varying_passage_root_retains_the_same_held_midpoint_law():
    s, e = constant()
    s = replace(s, classes=(replace(s.classes[0], restart_s_inv=0.2, hazard_s_inv=0.3),))
    full = advance_bulk(s, e, 1.0)
    c = full.coefficients
    prediction = predict_passage(s, e, 1.0, step_s=1.0)
    assert prediction.status == "PASS" and prediction.elapsed_s < 1.0
    dx, v = characteristic(c.characteristic_class, s.speed_mps, c.target_mps, prediction.elapsed_s)
    assert dx == pytest.approx(1.0, abs=1e-10)
    assert v == pytest.approx(prediction.speed_mps)


def test_identical_physical_classes_reduce_to_the_homogeneous_law():
    s, e = constant(0.7)
    c = s.classes[0]
    mixture = compile_bulk(
        tuple(
            replace(c, vehicle=replace(c.vehicle, name=name), mass_veh=mass)
            for name, mass in [("car", 5), ("scheduled_bus", 3), ("freight", 2)]
        ),
        speed_mps=s.speed_mps,
    )
    a, b = advance_bulk(s, e, 3), advance_bulk(mixture, e, 3)
    assert a.distance_m == pytest.approx(b.distance_m, abs=1e-12)
    assert a.state.speed_mps == pytest.approx(b.state.speed_mps, abs=1e-12)


def test_kinetic_cli_runs_real_oracles(tmp_path):
    import subprocess
    import sys
    import json

    out = tmp_path / "kinetic.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.v1",
            "physics-oracles",
            "--suite",
            "kinetic",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    report = json.loads(out.read_text())
    assert report["status"] == "PASS" and len(report["cases"]) == 8
