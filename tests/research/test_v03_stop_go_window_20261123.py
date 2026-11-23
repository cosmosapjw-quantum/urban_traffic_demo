"""Behavior tests for the scoped clipped-motion/joint-service observer."""
from dataclasses import asdict, replace
import math

import pytest

from metroflow.foundation_kinetics import VehicleClass, characteristic
from metroflow.v1.stop_go_window_certificate import (
    BoundStatus, ClippedMotionLaw, ExAnteBasis, ForcingWindow, JointServiceWindow,
    NumericalEvaluationError, NumericalGuard, QueueRankBound, WindowPhase,
    evaluate_link_bound, motion_distance_lower,
)


def basis(until=100.0):
    return ExAnteBasis("declared-stop-go", "synthetic controls declared at t=0", 0, 0, until)


def fixture():
    b = basis()
    return dict(context=b.context, decision_s=0, entry_s=0, length_m=20,
                law=ClippedMotionLaw(2, 4, 1, 1),
                forcing=ForcingWindow(b, 8, 16),
                service=JointServiceWindow.from_marginals(
                    basis=b, window_s=10, capacity_veh_s=2,
                    green_integral_lower_veh=14, receiving_integral_lower_veh=14),
                rank=QueueRankBound(b, 5))


def reference_motion_hit(length=20.0):
    vehicle = VehicleClass(response_s=2, accel_mps2=1, brake_mps2=1)
    clock = position = speed = 0.0
    for _ in range(30):
        for target in (0.0, 4.0):
            dx, end_speed = characteristic(vehicle, speed, target, 4)
            if position + dx >= length:
                lo, hi = 0.0, 4.0
                for _ in range(65):
                    middle = (lo + hi) / 2
                    if position + characteristic(vehicle, speed, target, middle)[0] >= length:
                        hi = middle
                    else:
                        lo = middle
                return clock + (lo + hi) / 2
            clock += 4
            position += dx
            speed = end_speed
    raise AssertionError("reference horizon insufficient")


def test_constructive_clipped_motion_and_joint_service_give_34_seconds():
    result = evaluate_link_bound(**fixture())
    assert result.status is BoundStatus.BOUND_EVALUATED
    assert result.motion.windows_used == 3
    assert result.motion.upper_time_s == 24
    assert result.service.service_mass_lower_veh == 8
    assert result.exit_upper_s == 34
    assert 15 < reference_motion_hit() < 16
    assert result.exit_upper_s < 36  # separate, declared alternative lower
    assert "not interval-certified" in result.numerical_semantics


def test_positive_marginals_without_overlap_do_not_claim_positive_service():
    args = fixture()
    args["service"] = JointServiceWindow.from_marginals(
        basis=basis(), window_s=10, capacity_veh_s=2,
        green_integral_lower_veh=10, receiving_integral_lower_veh=10)
    result = evaluate_link_bound(**args)
    assert result.status is BoundStatus.HORIZON_UNCERTIFIED
    assert result.exit_upper_s is None
    assert result.service.service_mass_lower_veh == 0
    # Direct joint knowledge is genuinely stronger than these two marginals.
    args["service"] = JointServiceWindow(basis(), 10, 2, 10)
    assert evaluate_link_bound(**args).exit_upper_s == 34


@pytest.mark.parametrize("component", ["forcing", "service", "rank"])
def test_future_delivered_guarantee_is_rejected(component):
    args = fixture()
    args[component] = replace(args[component],
                              basis=replace(args[component].basis, available_at_s=1))
    with pytest.raises(ValueError, match="not available"):
        evaluate_link_bound(**args)


@pytest.mark.parametrize("component", ["forcing", "service", "rank"])
def test_changed_context_is_not_silently_reused(component):
    args = fixture()
    args[component] = replace(args[component],
                              basis=replace(args[component].basis, context="different-field"))
    with pytest.raises(ValueError, match="context"):
        evaluate_link_bound(**args)


def test_insufficient_motion_horizon_is_not_physical_unreachability():
    args = fixture()
    args["forcing"] = replace(args["forcing"], basis=basis(16))
    result = evaluate_link_bound(**args)
    assert result.status is BoundStatus.HORIZON_UNCERTIFIED
    assert result.motion.available_windows == 2
    assert result.motion.lower_distance_m < 20
    assert result.exit_upper_s is None
    assert reference_motion_hit() < 16  # this witness physically reaches the endpoint


def test_node_service_horizon_cannot_be_extended_to_obtain_success():
    args = fixture()
    args["service"] = replace(args["service"], basis=basis(33))
    result = evaluate_link_bound(**args)
    assert result.status is BoundStatus.HORIZON_UNCERTIFIED
    assert result.motion.upper_time_s == 24
    assert result.service.windows_needed == 1
    assert result.exit_upper_s is None


def test_rank_bound_must_cover_unknown_actual_ready_time():
    args = fixture()
    args["rank"] = replace(args["rank"], basis=basis(23))
    result = evaluate_link_bound(**args)
    assert result.status is BoundStatus.HORIZON_UNCERTIFIED
    assert "every possible ready time" in result.reason


def test_aligned_forcing_adds_phase_and_drops_untransported_initial_memory():
    args = fixture()
    args.update(entry_s=1, initial_speed_lower_m_s=2)
    args["forcing"] = replace(args["forcing"], phase=WindowPhase.ALIGNED, alignment_origin_s=0)
    result = evaluate_link_bound(**args)
    assert result.motion.window_start_s == 8
    assert result.motion.ignored_phase_delay_s == 7
    assert result.motion.initial_speed_lower_used_m_s == 0
    assert result.motion.upper_time_s == 32
    assert result.exit_upper_s == 42


def test_aligned_service_waits_for_next_boundary():
    args = fixture()
    args["service"] = replace(args["service"], phase=WindowPhase.ALIGNED, alignment_origin_s=0)
    result = evaluate_link_bound(**args)
    assert result.service.window_start_s == 30
    assert result.exit_upper_s == 40


def test_binary_float_just_after_boundary_is_not_rounded_back_to_it():
    args = fixture()
    args["entry_s"] = math.nextafter(8.0, math.inf)
    args["forcing"] = replace(args["forcing"], phase=WindowPhase.ALIGNED, alignment_origin_s=0)
    result = evaluate_link_bound(**args)
    assert result.motion.window_start_s == 16


def test_no_complete_valid_window_is_uncertified():
    args = fixture()
    args["forcing"] = replace(args["forcing"], basis=basis(7))
    result = evaluate_link_bound(**args)
    assert result.status is BoundStatus.HORIZON_UNCERTIFIED
    assert result.motion.available_windows == 0


def test_impossible_forcing_mass_and_marginal_capacity_are_invalid():
    args = fixture()
    args["forcing"] = replace(args["forcing"], forcing_integral_lower_m=33)
    with pytest.raises(ValueError, match="forcing integral"):
        evaluate_link_bound(**args)
    with pytest.raises(ValueError, match="marginal exceeds"):
        JointServiceWindow.from_marginals(
            basis=basis(), window_s=10, capacity_veh_s=2,
            green_integral_lower_veh=21, receiving_integral_lower_veh=10)


def test_guard_prevents_promoting_an_unseparated_float_threshold():
    args = fixture()
    evaluation = motion_distance_lower(args["law"], args["forcing"], 3)
    args["length_m"] = evaluation.lower_m
    result = evaluate_link_bound(**args)
    assert result.motion.windows_used == 4
    assert result.motion.lower_distance_m - result.motion.distance_guard_m >= args["length_m"]


def test_numeric_range_failure_is_separate_from_physical_horizon():
    args = fixture()
    args["law"] = ClippedMotionLaw(1e300, 4, 1, 1)
    args["forcing"] = ForcingWindow(basis(), 1e-300, 1e-300)
    with pytest.raises(NumericalEvaluationError, match="underflows"):
        evaluate_link_bound(**args)


def test_spatial_and_mass_unit_rescaling_preserve_time_predictions():
    args = fixture()
    baseline = evaluate_link_bound(**args)
    scale = 1000.0
    args["length_m"] *= scale
    args["law"] = ClippedMotionLaw(2, 4*scale, scale, scale)
    args["forcing"] = replace(args["forcing"], forcing_integral_lower_m=16*scale)
    args["guard"] = NumericalGuard(absolute_distance_m=1e-10*scale)
    args["service"] = JointServiceWindow.from_marginals(
        basis=basis(), window_s=10, capacity_veh_s=2*scale,
        green_integral_lower_veh=14*scale, receiving_integral_lower_veh=14*scale)
    args["rank"] = QueueRankBound(basis(), 5*scale)
    scaled = evaluate_link_bound(**args)
    assert scaled.motion.upper_time_s == baseline.motion.upper_time_s
    assert scaled.exit_upper_s == baseline.exit_upper_s


@pytest.mark.parametrize("accel,brake", [(0.1,0.1), (1,0.1), (1,1), (10,10)])
def test_clipped_reference_dominates_lower_and_unclipped_pulse_attains_it(accel,brake):
    args = fixture()
    law = ClippedMotionLaw(2,4,accel,brake)
    vehicle = VehicleClass(response_s=2,accel_mps2=accel,brake_mps2=brake)
    position = speed = 0.0
    for n in range(1,9):
        for target in (0,4):
            dx,speed=characteristic(vehicle,speed,target,4)
            position+=dx
        value=motion_distance_lower(law,args["forcing"],n)
        assert position+1e-10 >= value.lower_m
        if accel >= 2 and brake >= 2:
            assert abs(position-value.lower_m) < 1e-10


def test_eta_one_does_not_make_braking_clipping_sharp():
    args = fixture()
    law = ClippedMotionLaw(2,4,10,0.1)
    vehicle = VehicleClass(response_s=2,accel_mps2=10,brake_mps2=0.1)
    position = speed = 0.0
    for target in (0,4,0,4):
        dx,speed=characteristic(vehicle,speed,target,4)
        position+=dx
    value=motion_distance_lower(law,args["forcing"],2)
    assert value.eta == 1
    assert position-value.lower_m > 1


def test_old_positive_speed_probe_is_inapplicable_at_zero_floor():
    from metroflow.v1.finite_response_probe_certificate import CompletedPassage, ResponseProbeCertificate
    probe=CompletedPassage("old-context",0,1,1,1)
    with pytest.raises(ValueError, match="positive ordered speed"):
        ResponseProbeCertificate("old-context",probe,1,2,0,4)


def test_same_inputs_have_deterministic_results():
    assert asdict(evaluate_link_bound(**fixture())) == asdict(evaluate_link_bound(**fixture()))
