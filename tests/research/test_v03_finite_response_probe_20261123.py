"""Focused finite-response observer checks; no native production solver."""
from fractions import Fraction
import math
import pytest

from metroflow.v1.finite_response_probe_certificate import (
    CompletedPassage, ResponseProbeCertificate,
)


def certificate(*, tau=10, decision=16, a=1, b=3, speed=2):
    return ResponseProbeCertificate(
        "corridor-A", CompletedPassage("corridor-A", 10, 15, 16, 5 * speed),
        decision, tau, a, b,
    )


def test_probe_rejects_wrong_measure_and_noncausal_delivery():
    with pytest.raises(ValueError, match="matched"):
        CompletedPassage("A", 10, 15, 16, 10, kind="event_birth_age")
    with pytest.raises(ValueError, match="causal"):
        CompletedPassage("A", 10, 15, 14, 10)
    with pytest.raises(ValueError, match="positive"):
        CompletedPassage("A", 10, 10, 11, 10)


def test_certificate_requires_delivered_same_context_compatible_physics():
    probe = CompletedPassage("A", 10, 15, 16, 10)
    with pytest.raises(ValueError, match="contexts"):
        ResponseProbeCertificate("B", probe, 16, 10, 1, 3)
    with pytest.raises(ValueError, match="delivered"):
        ResponseProbeCertificate("A", probe, 15, 10, 1, 3)
    with pytest.raises(ValueError, match="contradict"):
        ResponseProbeCertificate("A", probe, 16, 10, 2.1, 3)
    with pytest.raises(ValueError, match="positive"):
        ResponseProbeCertificate("A", probe, 16, 10, 0, 3)
    with pytest.raises(ValueError, match="finite"):
        ResponseProbeCertificate("A", probe, math.inf, 10, 1, 3)


def test_probe_speed_intervals_and_future_time_domain():
    c = certificate()
    assert c.memory_weight == pytest.approx(0.7707470412683991, abs=1e-15)
    assert c.exit_speed_bounds_m_s == pytest.approx((1.770747041268399, 2.229252958731601))
    assert c.decision_speed_bounds_m_s == pytest.approx((1.6974007627801533, 2.3025992372198467))
    with pytest.raises(ValueError, match="precede"):
        c.duration_bounds(15, 10)
    with pytest.raises(ValueError, match="negative"):
        c.distance_bounds(16, -1)


def test_actual_constant_solution_is_enclosed_and_informs_route_choice():
    c = certificate()
    band = c.duration_bounds(16, 10)
    assert 10 / 3 < band.lower_s < 5 < band.upper_s < 7 < 10
    assert band.lower_s == pytest.approx(4.1180114937786385, abs=1e-10)
    assert band.upper_s == pytest.approx(6.622438555153098, abs=1e-10)
    assert max(hi - lo for lo, hi in (
        band.lower_root_bracket_s, band.upper_root_bracket_s)) <= 1e-11
    assert min({"A": 10, "B": 7}, key={"A": 10, "B": 7}.get) == "B"
    assert min({"A": band.upper_s, "B": 7},
               key={"A": band.upper_s, "B": 7}.get) == "A"


def test_exact_rational_dominance_discriminator_is_strict():
    # Analytic exponential inequalities are proved in the accompanying note.
    lower_distance_at_7 = Fraction(7) + Fraction(17010, 5057)
    assert lower_distance_at_7 > 10
    assert lower_distance_at_7 - 10 == Fraction(1839, 5057)


def test_extreme_forcing_endpoint_witnesses_are_physically_admissible():
    c = certificate()
    tau, duration, length = 10, 5, 10
    integral_decay = tau * (1 - math.exp(-duration / tau))
    for forcing, endpoint in zip((1, 3), c.exit_speed_bounds_m_s):
        initial = (length - forcing * (duration - integral_decay)) / integral_decay
        assert 1 <= initial <= 3
        actual_length = forcing * duration + (initial - forcing) * integral_decay
        actual_exit = forcing + (initial - forcing) * math.exp(-duration / tau)
        assert actual_length == pytest.approx(length, abs=2e-14)
        assert actual_exit == pytest.approx(endpoint, abs=2e-14)


def test_forgetting_and_relaxation_limits():
    long_delay = certificate(decision=10000).duration_bounds(10000, 10)
    assert long_delay.lower_s == pytest.approx(10 / 3, abs=1e-10)
    assert long_delay.upper_s == pytest.approx(10, abs=1e-10)
    assert certificate(tau=.001).memory_weight == 0
    near_constant = certificate(tau=1e8).duration_bounds(16, 10)
    assert abs(near_constant.lower_s - 5) < 1e-6
    assert abs(near_constant.upper_s - 5) < 1e-6


def test_units_rescaling_preserves_the_same_physical_prediction():
    original = certificate().duration_bounds(16, 10)
    spatial = ResponseProbeCertificate(
        "A", CompletedPassage("A", 10, 15, 16, 70), 16, 10, 7, 21,
    ).duration_bounds(16, 70)
    temporal = ResponseProbeCertificate(
        "A", CompletedPassage("A", 30, 45, 48, 10), 48, 30, 1 / 3, 1,
    ).duration_bounds(48, 10)
    assert spatial.lower_s == pytest.approx(original.lower_s, abs=1e-10)
    assert spatial.upper_s == pytest.approx(original.upper_s, abs=1e-10)
    assert temporal.lower_s == pytest.approx(3 * original.lower_s, abs=1e-10)
    assert temporal.upper_s == pytest.approx(3 * original.upper_s, abs=1e-10)


def test_equal_speed_bounds_collapse_exactly():
    c = certificate(a=2, b=2)
    assert c.exit_speed_bounds_m_s == (2, 2)
    band = c.duration_bounds(16, 10)
    assert band.lower_s == band.upper_s == 5
    assert c.distance_bounds(16, 5) == (10, 10)


def test_increasing_departures_remain_fifo_with_nested_global_bounds():
    c = certificate()
    previous_lower = previous_upper = -math.inf
    for t in (16, 17, 20, 25, 40, 100):
        band = c.duration_bounds(t, 10)
        assert 10 / 3 <= band.lower_s <= band.upper_s <= 10
        assert t + band.lower_s > previous_lower
        assert t + band.upper_s > previous_upper
        previous_lower, previous_upper = t + band.lower_s, t + band.upper_s


def test_insufficient_numerical_budget_reports_unresolved_root():
    with pytest.raises(ArithmeticError, match="not resolved"):
        certificate().duration_bounds(16, 10, max_iterations=1)
    with pytest.raises(ValueError, match="positive"):
        certificate().duration_bounds(16, 0)
    with pytest.raises(ValueError, match="positive"):
        certificate().duration_bounds(16, 10, tolerance_s=0)
