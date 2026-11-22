"""Finite-horizon route delay quantile stability under matched exit clocks."""
from fractions import Fraction as F
from itertools import product

from metroflow.v1.fifo_censored_quantiles import (
    FIFOBlock, ServiceCurve, FiniteFIFOQuantiles, service_dominates,
)


SOURCE=(
    FIFOBlock(1,F(0),F(2),F(0)),
    FIFOBlock(2,F(2),F(3),F(1)),
    FIFOBlock(1,F(3),F(5),F(1)),
    FIFOBlock(2,F(5),F(6),F(2)),
)


def test_small_cohort_exit_time_shift_bounds_every_finite_route_quantile():
    a=ServiceCurve(((F(0),F(0)),(F(12),F(6)),(F(20),F(6))))
    b=ServiceCurve(((F(0),F(0)),(F(120,11),F(6)),(F(20),F(6))))
    assert service_dominates(b,a)
    slow=FiniteFIFOQuantiles(SOURCE,a,F(20))
    faster=FiniteFIFOQuantiles(SOURCE,b,F(20))
    # Coupled per-source mass labels: slow T=2z; faster T=20z/11.
    # Maximum absolute exit-clock displacement for z∈[0,6] is 12/11s.
    eps=F(12,11)
    for route,p in product((1,2),(F(i,32) for i in range(1,33))):
        # Recreate the rational iterator on every inner loop; values here
        # come from a full finite route denominator, not completed-only mass.
        q1=slow.quantile(route,p)
        q2=faster.quantile(route,p)
        assert q1 is not None and q2 is not None
        assert F(0)<=q1-q2<=eps
    # A finite-horizon censor transition can still change a quantile from
    # infinity to finite; no absolute Lipschitz claim is made in that case.
    slow7=FiniteFIFOQuantiles(SOURCE,a,F(7))
    fast7=FiniteFIFOQuantiles(SOURCE,b,F(7))
    assert slow7.quantile(2,F(3,4)) is None
    assert fast7.quantile(2,F(3,4)) is None
