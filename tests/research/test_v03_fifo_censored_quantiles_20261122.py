"""Finite-horizon FIFO pathwise route delay distribution: independent checks."""
from fractions import Fraction as F
import pytest
from metroflow.v1.fifo_censored_quantiles import (
    FIFOBlock, ServiceCurve, FiniteFIFOQuantiles, service_dominates,
)


def fixtures():
    source=(
        FIFOBlock(1,F(0),F(2),F(0)),
        FIFOBlock(2,F(2),F(3),F(1)),
        FIFOBlock(1,F(3),F(5),F(1)),
        FIFOBlock(2,F(5),F(6),F(2)),
    )
    slow=ServiceCurve(((F(0),F(0)),(F(12),F(6)),(F(20),F(6))))
    fast=ServiceCurve(((F(0),F(0)),(F(6),F(6)),(F(20),F(6))))
    return source,slow,fast


def test_exact_route_censored_probability_and_quantile_nonstationary():
    source,slow,fast=fixtures()
    assert service_dominates(fast,slow)
    s=FiniteFIFOQuantiles(source,slow,F(7))
    f=FiniteFIFOQuantiles(source,fast,F(7))
    assert s.route_mass(1)==4 and s.route_mass(2)==2
    assert (s.completion(1),f.completion(1))==(F(5,8),F(1))
    assert (s.completion(2),f.completion(2))==(F(1,2),F(1))
    assert (s.cdf(1,F(3)),f.cdf(1,F(3)))==(F(3,8),F(3,4))
    assert (s.cdf(2,F(3)),f.cdf(2,F(3)))==(F(0),F(1,2))
    assert (s.quantile(1,F(1,2)),f.quantile(1,F(1,2)))==(F(4),F(2))
    assert (s.quantile(2,F(3,4)),f.quantile(2,F(3,4)))==(None,F(7,2))
    for threshold in [F(0),F(1,2),F(1),F(2),F(3),F(4),F(7),F(100)]:
        assert f.cdf(1,threshold)>=s.cdf(1,threshold)
        assert f.cdf(2,threshold)>=s.cdf(2,threshold)


def test_censoring_uses_all_original_route_mass_not_selected_completed_mass():
    source,slow,fast=fixtures()
    s=FiniteFIFOQuantiles(source,slow,F(7))
    assert s.cdf(1,F(100))==F(5,8)
    assert s.cdf(2,F(100))==F(1,2)
    assert s.quantile(1,F(3,4)) is None
    assert s.quantile(2,F(3,4)) is None


def test_physically_unavailable_birth_source_and_bad_service_rejected():
    source,slow,fast=fixtures()
    with pytest.raises(ValueError):
        FiniteFIFOQuantiles([FIFOBlock(1,F(0),F(2),F(2))],fast,F(7))
    with pytest.raises(ValueError):
        ServiceCurve(((F(0),F(0)),(F(1),F(2)),(F(2),F(1))))
    with pytest.raises(ValueError):
        FiniteFIFOQuantiles([FIFOBlock(1,F(0),F(2),F(0)),
                            FIFOBlock(2,F(1),F(3),F(0))],slow,F(7))


def test_service_pointwise_order_not_merely_final_capacity():
    a=ServiceCurve(((F(0),F(0)),(F(3),F(3)),(F(6),F(3))))
    b=ServiceCurve(((F(0),F(0)),(F(3),F(1)),(F(6),F(4))))
    assert not service_dominates(b,a)
    assert not service_dominates(a,b)


def test_finished_only_average_can_reverse_due_to_different_completion_sets():
    # Two labelled unit-mass cohorts: older first finishes at age 1 under both.
    # Later second finishes at age 8 only with service improvement before H=10.
    source=(FIFOBlock(1,F(0),F(1),F(0)),FIFOBlock(1,F(1),F(2),F(0)))
    slow=ServiceCurve(((F(0),F(0)),(F(1),F(1)),(F(10),F(1)),(F(100),F(2))))
    fast=ServiceCurve(((F(0),F(0)),(F(1),F(1)),(F(8),F(2)),(F(100),F(2))))
    assert service_dominates(fast,slow)
    a=FiniteFIFOQuantiles(source,slow,F(10))
    b=FiniteFIFOQuantiles(source,fast,F(10))
    assert a.completion(1)==F(1,2) and b.completion(1)==1
    # Fixed-input censored law remains ordered despite completed-only shift.
    assert b.quantile(1,F(3,4)) is not None
    assert a.quantile(1,F(3,4)) is None
