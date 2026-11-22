"""Exact finite-horizon age-excess route transport, independent physical checks."""
from fractions import Fraction as F
import pytest
from metroflow.v1.age_excess_transport import (
    AgeCohort, AgeBoundary, finite_age_excess_transport
)

def test_two_completed_route_ages_reconstruct_k_and_squared_delay():
    initial=(AgeCohort(1,F(1),F(0)),AgeCohort(1,F(1),F(0)))
    events=(
        AgeBoundary(F(3),1,"out",F(1),F(0)),
        AgeBoundary(F(5),1,"out",F(1),F(0)),
    )
    a=finite_age_excess_transport(F(0),F(5),initial,events,
                                   [F(0),F(2),F(3),F(4),F(5)])
    x=a[(1,F(2))]
    assert (x.output_loss,x.tail_stock_time,x.entry_loss,
            x.initial_loss,x.terminal_loss)==(4,4,0,0,0)
    assert x.output_mass==2 and x.route_source_mass==2
    assert a[(1,F(0))].output_loss==8
    assert a[(1,F(3))].output_loss==2
    assert a[(1,F(5))].output_loss==0
    assert a[(1,F(3))].strict_output_tail_mass==1
    assert a[(1,F(3))].weak_output_tail_mass==2
    assert a[(1,F(3))].completed_cdf==F(1,2)
    assert a[(1,F(3))].fixed_source_cdf==F(1,2)
    # Independently integrate the piecewise linear K(u) at knots 0,3,5.
    squared=2*(F(3)*(8+2)/2+F(2)*(2+0)/2)
    assert squared==34==a[(1,F(0))].output_delay_square


def test_unfinished_route_stock_not_miscounted_as_completed_output():
    out=finite_age_excess_transport(F(0),F(5),
        (AgeCohort(1,2,0),),
        (AgeBoundary(F(3),1,"out",1,0),),
        (F(0),F(2),F(3)))
    x=out[(1,F(2))]
    assert x.tail_stock_time==4
    assert x.terminal_loss==3
    assert x.output_loss==1
    assert x.output_mass==1 and x.route_source_mass==2
    assert x.fixed_source_cdf==F(0)   # at u=2 no completed delay <=2
    assert out[(1,F(3))].fixed_source_cdf==F(1,2)
    assert out[(1,F(3))].completed_cdf==1


def test_external_preaged_ingress_and_internal_other_route():
    res=finite_age_excess_transport(F(0),F(5),(),
        (AgeBoundary(F(2),2,"in",1,-1),
         AgeBoundary(F(3),1,"in",2,3),
         AgeBoundary(F(4),2,"out",1,-1),
         AgeBoundary(F(5),1,"out",2,3)),
        (F(2),))
    b=res[(2,F(2))]
    assert (b.entry_loss,b.tail_stock_time,b.output_loss,
            b.terminal_loss)==(1,2,3,0)
    assert res[(1,F(2))].output_loss==0
    assert res[(1,F(2))].route_source_mass==2


def test_time_origin_translation_and_threshold_atoms():
    src=(AgeCohort(1,2,0),)
    ev=(AgeBoundary(F(3),1,"out",1,0),
        AgeBoundary(F(5),1,"out",1,0))
    baseline=finite_age_excess_transport(F(0),F(5),src,ev,(F(2),F(3)))
    for shift in (F(-13),F(7,3),F(109)):
        moved=finite_age_excess_transport(
            shift,F(5)+shift,
            (AgeCohort(1,2,shift),),
            tuple(AgeBoundary(e.time+shift,e.route,e.direction,
                              e.mass,e.birth+shift) for e in ev),
            (F(2),F(3)))
        assert moved==baseline


def test_wrong_events_and_nonphysical_ages_fail_closed():
    with pytest.raises(ValueError):
        finite_age_excess_transport(F(0),F(5),(),
            (AgeBoundary(F(3),1,"out",1,0),),(F(2),))
    with pytest.raises(ValueError):
        finite_age_excess_transport(F(0),F(5),(),
            (AgeBoundary(F(2),1,"in",1,3),),(F(2),))
    with pytest.raises(ValueError):
        finite_age_excess_transport(F(0),F(5),(),
            (AgeBoundary(F(2),1,"in",-1,0),),(F(2),))
    with pytest.raises(ValueError):
        finite_age_excess_transport(F(0),F(5),(AgeCohort(1,1,1),),(),(F(2),))
