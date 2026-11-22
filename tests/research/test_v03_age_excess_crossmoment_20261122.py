"""Independent bridge: age-excess stop-loss recovers original first/second moments."""
from fractions import Fraction as F
from metroflow.v1.age_excess_transport import (
    AgeCohort,AgeBoundary,finite_age_excess_transport,
)
from metroflow.v1.transient_dispersion import (
    QuadraticBoundaryEvent,finite_second_residence_balance,
)


def test_exact_completed_delay_age_excess_bridge_to_finite_second_moment():
    u=(F(0),F(3),F(5))
    excess=finite_age_excess_transport(
        F(0),F(5),(AgeCohort(1,2,0),),
        (AgeBoundary(F(3),1,"out",1,0),AgeBoundary(F(5),1,"out",1,0)),u)
    square=finite_second_residence_balance(
        F(0),F(5),{1:(F(2),F(0),F(0))},[
            QuadraticBoundaryEvent(F(3),1,"out",F(1),F(0),F(0)),
            QuadraticBoundaryEvent(F(5),1,"out",F(1),F(0),F(0)),
        ])[1]
    assert excess[(1,F(0))].output_loss==square.output_age1==F(8)
    assert excess[(1,F(0))].output_delay_square==square.output_age2==F(34)
    # Exact piecewise linear stop-loss integral by physical output-age knots.
    area=(F(3)*(excess[(1,F(0))].output_loss+excess[(1,F(3))].output_loss)/2
          +F(2)*(excess[(1,F(3))].output_loss+excess[(1,F(5))].output_loss)/2)
    assert 2*area==square.output_age2


def test_external_preaged_source_matches_second_birth_moment():
    x=finite_age_excess_transport(F(0),F(5),(),
        (AgeBoundary(F(2),2,"in",1,-1),
         AgeBoundary(F(4),2,"out",1,-1)),(F(0),F(2),F(5)))
    y=finite_second_residence_balance(F(0),F(5),{},
        (QuadraticBoundaryEvent(F(2),2,"in",F(1),F(-1),F(1)),
         QuadraticBoundaryEvent(F(4),2,"out",F(1),F(-1),F(1))))[2]
    assert x[(2,F(0))].output_loss==y.output_age1==F(5)
    assert x[(2,F(0))].output_delay_square==y.output_age2==F(25)
    assert x[(2,F(2))].entry_loss==1
    assert x[(2,F(2))].tail_stock_time==2
    assert x[(2,F(2))].output_loss==3
