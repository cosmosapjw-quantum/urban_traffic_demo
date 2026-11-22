"""Adversarial source-direct finite age transport, not using the stock solver.

Each trial computes physical resident interval and completed age-excess
independently from original birth/exit clocks, including unfinished tails.
No numerical approximation or statistical sampling.
"""
from fractions import Fraction as F
from itertools import product
from metroflow.v1.age_excess_transport import (
    AgeCohort,AgeBoundary,finite_age_excess_transport
)

def test_2880_exact_completed_censored_age_excess_cases():
    count=0
    for route,birth,exit_time,horizon,mass,u in product(
        (0,1,2),(-5,-2,0),(2,4,7,12),(3,5,9,15),
        (F(1),F(3,2)),(0,1,2,3,4,5,6,8,10,16)
    ):
        birth=F(birth);exit_time=F(exit_time);T=F(horizon);u=F(u)
        src=(AgeCohort(route,mass,birth),)
        finished=exit_time<=T
        events=(AgeBoundary(exit_time,route,"out",mass,birth),) if finished else ()
        x=finite_age_excess_transport(F(0),T,src,events,(u,))[(route,u)]
        end=exit_time if finished else T
        # Direct pointwise physical cohort occupancy, independent of μ solver.
        occupancy=mass*max(F(0),end-max(F(0),birth+u))
        completed=mass*max(F(0),exit_time-birth-u) if finished else F(0)
        terminal=mass*max(F(0),T-birth-u) if not finished else F(0)
        initially=mass*max(F(0),-birth-u)
        assert x.tail_stock_time==occupancy
        assert x.output_loss==completed
        assert x.terminal_loss==terminal
        assert x.initial_loss==initially
        assert x.entry_loss==0
        assert x.output_mass==(mass if finished else F(0))
        assert x.route_source_mass==mass
        assert x.output_delay_square==(mass*(exit_time-birth)**2 if finished else F(0))
        assert x.fixed_source_cdf==(
            F(1) if finished and exit_time-birth<=u else F(0)
        )
        assert x.completed_cdf==(
            None if not finished else
            (F(1) if exit_time-birth<=u else F(0))
        )
        assert x.output_loss==x.tail_stock_time+x.initial_loss-x.terminal_loss
        count+=1
    assert count==2880


def test_simultaneous_identical_source_events_have_no_spurious_negative_stock():
    # A physically valid zero-residence in/out pair at the same clock may
    # be listed in either order in the same boundary group.
    for events in (
        (AgeBoundary(F(3),1,"in",2,3),
         AgeBoundary(F(3),1,"out",2,3)),
        (AgeBoundary(F(3),1,"out",2,3),
         AgeBoundary(F(3),1,"in",2,3)),
    ):
        x=finite_age_excess_transport(F(0),F(5),(),events,(F(0),F(2)))
        for u in (F(0),F(2)):
            o=x[(1,u)]
            assert o.output_loss==o.tail_stock_time==o.entry_loss==0
            assert o.terminal_loss==0
            assert o.route_source_mass==2
            assert o.output_mass==2
