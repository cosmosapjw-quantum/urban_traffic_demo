"""Age-excess observer supplies rigorous finite-horizon censored tail bounds."""
from fractions import Fraction as F
import pytest
from metroflow.v1.age_excess_transport import AgeCohort,AgeBoundary,finite_age_excess_transport


def test_exact_physical_stoploss_bounds_censored_original_route_tail():
    res=finite_age_excess_transport(F(0),F(5),(AgeCohort(1,2,0),),
       (AgeBoundary(F(3),1,"out",1,0),
        AgeBoundary(F(5),1,"out",1,0)),(F(2),F(3)))
    # K(3)=2, excess threshold Δ=2, so original full-route upper bound
    # P_completed(w>=5) <= (K(3)/2)/M =1/2, attained by exit at age5.
    assert res[(1,F(3))].censored_tail_upper_bound(F(2))==F(1,2)
    # Loose but truthful upper bound at u2, threshold v5:
    assert res[(1,F(2))].censored_tail_upper_bound(F(3))==F(2,3)


def test_terminal_unfinished_mass_always_stays_in_censored_tail_bound():
    res=finite_age_excess_transport(F(0),F(5),(AgeCohort(1,2,0),),
       (AgeBoundary(F(3),1,"out",1,0),),(F(3),))
    assert res[(1,F(3))].output_mass==1
    assert res[(1,F(3))].route_source_mass==2
    assert res[(1,F(3))].censored_tail_upper_bound(F(2))==F(1,2)
    with pytest.raises(ValueError):
        res[(1,F(3))].censored_tail_upper_bound(F(0))
    with pytest.raises(ValueError):
        res[(1,F(3))].censored_tail_upper_bound(F(-1))
