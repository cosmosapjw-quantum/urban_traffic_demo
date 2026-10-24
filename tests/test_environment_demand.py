import math
import pytest
from metroflow.environment.demand import balance_od, DemandInfeasible


def test_both_worker_and_job_margins_and_cost_deterrence():
    r=balance_od((60.,40.),(50.,50.),((0.,1000.),(1000.,0.)),tau_s=100.)
    assert sum(r.matrix[0])==pytest.approx(60.,abs=1e-6)
    assert sum(r.matrix[1])==pytest.approx(40.,abs=1e-6)
    assert sum(row[0] for row in r.matrix)==pytest.approx(50.,abs=1e-6)
    assert r.matrix[0][0]>r.matrix[0][1]


def test_unreachable_pairs_are_structural_zeros():
    r=balance_od((20.,30.),(20.,30.),((0.,math.inf),(math.inf,0.)))
    assert r.matrix==((20.,0.),(0.,30.))


def test_hall_infeasible_support_rejected_before_iterations():
    # Every row/column has support, but row0 cannot put 9 units in a 5-unit column.
    with pytest.raises(DemandInfeasible):
        balance_od((9.,1.),(5.,5.),((0.,math.inf),(0.,0.)))


def test_stock_imbalance_not_silently_renormalized():
    with pytest.raises(DemandInfeasible):balance_od((100.,),(70.,),((0.,),))


def test_zero_margins_and_input_validation():
    assert balance_od((0.,),(0.,),((0.,),)).matrix==((0.,),)
    with pytest.raises(ValueError):balance_od((1.,),(1.,),((-1.,),))
    with pytest.raises(ValueError):balance_od((1.,),(1.,),((0.,),),tau_s=0.)


def test_iteration_exhaustion_is_not_success():
    with pytest.raises(RuntimeError):
        balance_od((90.,10.),(20.,80.),((0.,20.),(20.,0.)),tau_s=5.,max_iter=1)
