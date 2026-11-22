"""Finite-horizon route age-stock balance: exact rational physical fixtures."""
from fractions import Fraction as F
import pytest
from metroflow.v1.transient_residence import BoundaryEvent, finite_residence_balance

def test_truncated_traffic_window_keeps_route_specific_endpoint_ages():
    x=finite_residence_balance(
        F(0),F(5),
        {1:(F(2),F(0)), 2:(F(0),F(0)), 3:(F(1),F(-2))},
        [
            BoundaryEvent(F(1),3,"out",F(1),F(-2)),
            BoundaryEvent(F(2),2,"in",F(1),F(-1)),
            BoundaryEvent(F(3),1,"out",F(1),F(0)),
            BoundaryEvent(F(4),2,"out",F(1),F(-1)),
        ],
    )
    assert x[1].area==F(8) and x[1].output_delay==F(3)
    assert x[1].terminal_age==F(5) and x[1].entry_age==0
    assert x[2].area==F(2) and x[2].entry_age==F(3)
    assert x[2].output_delay==F(5) and x[2].terminal_age==0
    assert x[3].area==F(1) and x[3].initial_age==F(2)
    assert x[3].output_delay==F(3)
    assert sum(s.area for s in x.values())==F(11)
    assert sum(s.output_delay for s in x.values())==F(11)


def test_same_clock_internal_transfer_cancels_even_if_exit_listed_first():
    left=finite_residence_balance(F(0),F(5),
        {7:(F(1),F(0))},
        [BoundaryEvent(F(2),7,"out",F(1),F(0))])
    right=finite_residence_balance(F(0),F(5),{},
        [BoundaryEvent(F(2),7,"in",F(1),F(0)),
         BoundaryEvent(F(4),7,"out",F(1),F(0))])
    total=finite_residence_balance(F(0),F(5),{7:(F(1),F(0))},
        [BoundaryEvent(F(4),7,"out",F(1),F(0))])
    assert left[7].area+right[7].area==total[7].area==F(4)
    assert left[7].output_delay+right[7].output_delay-left[7].entry_age-right[7].entry_age==total[7].output_delay
    # Instantaneous same-clock physical source exchange has zero occupancy.
    swap=finite_residence_balance(F(0),F(5),{},
        [BoundaryEvent(F(2),8,"out",F(1),F(0)),
         BoundaryEvent(F(2),8,"in",F(1),F(0))])
    assert swap[8].area==0 and swap[8].output_delay==F(2)
    assert swap[8].entry_age==F(2)


def test_negative_stock_or_future_birth_is_rejected_without_fabricated_pass():
    with pytest.raises(ValueError):
        finite_residence_balance(F(0),F(5),{1:(F(1),F(0))},
            [BoundaryEvent(F(1),1,"out",F(2),F(0))])
    with pytest.raises(ValueError):
        finite_residence_balance(F(0),F(5),{},
            [BoundaryEvent(F(1),1,"in",F(1),F(2))])
    with pytest.raises(ValueError):
        finite_residence_balance(F(2),F(1),{},[])
