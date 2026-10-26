"""Small synthetic kinetic oracles; no full repository CI or city execution."""

from dataclasses import replace
import math

from ..foundation_kinetics import VehicleClass, PhaseBin, evolve, moments
from ..gap_transport import PairBin
from ..ordered_lane import distance_clock
from .city import CityContractError
from .kinetics import (
    ClassMass,
    KineticEnvironment,
    compile_bulk,
    coefficients,
    advance_bulk,
    predict_passage,
    latent_reference,
    pair_compatibility,
)


def kinetic_oracles():
    rows = []
    c = VehicleClass(response_s=5.0)
    s = compile_bulk((ClassMass(c, 10, 1, 0, 0),), speed_mps=2)
    e = KineticEnvironment(1000, 8, 0)
    r = advance_bulk(s, e, 2)
    exact_v = 8 - 6 * math.exp(-0.4)
    exact_x = 16 - 30 * (1 - math.exp(-0.4))
    old_dx, _ = distance_clock(2, 1, 8, 0.2, 0)
    rows.append(
        dict(
            case="constant_characteristic",
            status="PASS"
            if abs(r.distance_m - exact_x) < 1e-10 and abs(r.state.speed_mps - exact_v) < 1e-10
            else "NUMERICAL_ERROR",
            distance_m=r.distance_m,
            speed_mps=r.state.speed_mps,
            baseline_p_only_distance_m=old_dx,
        )
    )
    prediction = predict_passage(s, e, 100)
    residual = advance_bulk(s, e, prediction.elapsed_s).distance_m - 100
    rows.append(
        dict(
            case="same_law_first_passage",
            status="PASS" if abs(residual) < 1e-9 else "NUMERICAL_ERROR",
            elapsed_s=prediction.elapsed_s,
            residual_m=residual,
        )
    )
    reference = latent_reference(20, 0.2, 0.3, 3, 1, 20, 2)
    rows.append(
        dict(
            case="latent_continuous_reference",
            status="PASS"
            if abs(reference["stationary_variance_m2_s2"] - 38.4) < 1e-10
            and reference["mean_mps"] > reference["latent_binary_mean_mps"]
            else "MODEL_ERROR",
            **reference,
        )
    )
    c = VehicleClass(response_s=3, accel_mps2=100, brake_mps2=100)
    s = compile_bulk((ClassMass(c, 1, 1, 0.2, 0.3, 100),), speed_mps=20)
    e = KineticEnvironment(100, 20, 0)
    errors = []
    for dt in (0.5, 0.25, 0.125):
        current = s
        for _ in range(round(2 / dt)):
            current = advance_bulk(current, e, dt).state
        errors.append(abs(current.speed_mps - reference["mean_mps"]))
    rows.append(
        dict(
            case="temporal_refinement",
            status="PASS"
            if errors[1] < errors[0] / 3.5 and errors[2] < errors[1] / 3.5
            else "NUMERICAL_ERROR",
            dt_s=[0.5, 0.25, 0.125],
            speed_error_mps=errors,
        )
    )
    car = VehicleClass()
    truck = VehicleClass("freight", 12, 4, 0.5, 2, 3, 1.5, 12)
    s = compile_bulk((ClassMass(car, 3, 1, 0, 0), ClassMass(truck, 1, 0.2, 0, 0)))
    e = KineticEnvironment(1000, 30, 0)
    r = advance_bulk(s, e, 1)
    rows.append(
        dict(
            case="mixed_conservative_acceleration",
            status="PASS"
            if abs(r.state.speed_mps - 0.5) < 1e-10 and r.state.mass_veh == 4
            else "MODEL_ERROR",
            speed_mps=r.state.speed_mps,
            response_s=r.coefficients.response_s,
            target_mps=r.coefficients.target_mps,
        )
    )
    s = compile_bulk((ClassMass(car, 2),), speed_mps=10)
    e = KineticEnvironment(110, 20, 0)
    pairs = (PairBin(car, 1, 30, 10, 10), PairBin(car, 1, 70, 10, 10))
    report = pair_compatibility(s, e, pairs, ("car", "car"))
    heterogeneous = 0.15 * ((10 / 35) ** 2 + (10 / 75) ** 2)
    uniform = coefficients(s, e).hazards_s_inv[0]
    varied = moments(evolve(car, (PhaseBin(1, 4, 2), PhaseBin(1, 96, 2)), 1, 20))
    rows.append(
        dict(
            case="gap_closure_counterexample",
            status="PASS"
            if report["status"] == "PASS_NECESSARY_ONLY"
            and heterogeneous > uniform
            and varied[2] > 0
            else "MODEL_ERROR",
            pair_ledger=report,
            uniform_hazard_s_inv=uniform,
            heterogeneous_mean_hazard_s_inv=heterogeneous,
            kinetic_variance_m2_s2=varied[2],
        )
    )
    s = compile_bulk((ClassMass(car, 1),), speed_mps=20)
    e = KineticEnvironment(1000, 0, 0)
    r = advance_bulk(s, e, 0.1)
    rows.append(
        dict(
            case="abrupt_braking",
            status="PASS"
            if 19.6 - 1e-12 <= r.state.speed_mps < 20
            and predict_passage(s, e, 1000).status == "UNREACHABLE"
            else "MODEL_ERROR",
            speed_mps=r.state.speed_mps,
            distance_m=r.distance_m,
        )
    )
    rejected = False
    try:
        advance_bulk(s, replace(e, stamp_s=1), 1)
    except CityContractError:
        rejected = True
    rows.append(dict(case="future_observation", status="PASS" if rejected else "MODEL_ERROR"))
    return rows
