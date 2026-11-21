"""Causal FIFO time-resolved route delay and intervention theorem, exact rational tests."""
from fractions import Fraction as F
import pytest
from metroflow.v1.fifo_cohort_moments import CohortPacket,CohortPart
from metroflow.v1.fifo_age_transport import departure_age_snapshot, fifo_route_delay


def cohorts():
    return (
        CohortPacket((CohortPart(1,F(2),F(0)),CohortPart(2,F(1),F(1)))),
        CohortPacket((CohortPart(1,F(1),F(2)),CohortPart(2,F(1),F(3)))),
    )


def test_dynamic_age_and_first_moment_at_fixed_time_are_route_resolved():
    state=departure_age_snapshot(cohorts(),F(10),F(4))
    assert state.route_mass=={1:F(5,2),2:F(3,2)}
    assert state.route_birth_moment=={1:F(1),2:F(5,2)}
    assert state.route_age_moment=={1:F(24),2:F(25,2)}
    assert state.mean_departed_age=={1:F(48,5),2:F(25,3)}


def test_cumulative_real_exit_delays_decrease_under_pointwise_service_dominance():
    base=fifo_route_delay(cohorts(),((F(10),F(15),F(1)),))
    relieved=fifo_route_delay(cohorts(),((F(10),F(25,2),F(2)),))
    assert base.route_served_mass==relieved.route_served_mass=={1:F(3),2:F(2)}
    assert base.route_delay_total=={1:F(35),2:F(43,2)}
    assert relieved.route_delay_total=={1:F(63,2),2:F(75,4)}
    assert base.route_delay_total[1]-relieved.route_delay_total[1]==F(7,2)
    assert base.route_delay_total[2]-relieved.route_delay_total[2]==F(11,4)


def test_incomplete_schedule_and_negative_or_unphysical_rate_fail_closed():
    with pytest.raises(ValueError):
        fifo_route_delay(cohorts(),((F(10),F(11),F(-1)),))
    with pytest.raises(ValueError):
        fifo_route_delay(cohorts(),((F(10),F(11),F(1)),))


def test_route_delay_capacity_order_for_finite_exact_rational_rates():
    # Homogeneous fixed-source service clocks T_q(z)=10+z/q.
    # The theorem predicts route-by-route monotonicity without any
    # hypothesis that birth times are globally strictly increasing.
    trials=0
    for slow_rate in range(1,7):
        for fast_rate in range(slow_rate,7):
            slow=F(slow_rate)
            fast=F(fast_rate)
            one=fifo_route_delay(cohorts(),((F(10),F(10)+F(5)/slow,slow),))
            two=fifo_route_delay(cohorts(),((F(10),F(10)+F(5)/fast,fast),))
            assert all(two.route_delay_total[r]<=one.route_delay_total[r]
                       for r in (1,2))
            assert sum(two.route_served_mass.values(),F(0))==F(5)
            trials+=1
    assert trials==21
