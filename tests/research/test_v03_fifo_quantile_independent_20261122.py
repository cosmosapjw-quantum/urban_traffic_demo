"""Independent exact source-label integration versus route CDF implementation."""
from fractions import Fraction as F
from itertools import product

from metroflow.v1.fifo_censored_quantiles import (
    FIFOBlock, ServiceCurve, FiniteFIFOQuantiles, service_dominates
)


SOURCE=(
    FIFOBlock(1,F(0),F(2),F(0)),
    FIFOBlock(2,F(2),F(3),F(1)),
    FIFOBlock(1,F(3),F(5),F(1)),
    FIFOBlock(2,F(5),F(6),F(2)),
)
SLOW=ServiceCurve(((F(0),F(0)),(F(12),F(6)),(F(20),F(6))))
MIDDLE=ServiceCurve(((F(0),F(0)),(F(4),F(2)),(F(9),F(6)),(F(20),F(6))))
FAST=ServiceCurve(((F(0),F(0)),(F(6),F(6)),(F(20),F(6))))


def direct_source_label_mass_by_inverse(cohort, curve, horizon, bound):
    """Independent physical integration in mass z, not a service-at-deadline shortcut.

    Partition z at original cohort endpoints, cumulative service curve knots,
    and the original horizon S(H). In each positive-rate segment exit time is
    affine and we integrate z-length satisfying T(z)-birth <= bound.
    """
    split={F(cohort.z0),F(cohort.z1)}
    split.update(F(s) for _,s in curve.points
                 if F(cohort.z0) < F(s) < F(cohort.z1))
    cap=curve.value(horizon)
    if F(cohort.z0)<cap<F(cohort.z1):
        split.add(cap)
    keys=sorted(split)
    total=F(0)
    for lo,hi in zip(keys,keys[1:]):
        midpoint=(lo+hi)/2
        if midpoint>=cap:continue
        bracket=None
        for (ta,sa),(tb,sb) in zip(curve.points,curve.points[1:]):
            if F(sa)<midpoint<F(sb):
                bracket=(F(ta),F(sa),F(tb),F(sb))
                break
        if bracket is None:
            raise ArithmeticError("valid served source mass has no physical exit clock")
        ta,sa,tb,sb=bracket
        tleft=ta+(lo-sa)*(tb-ta)/(sb-sa)
        tright=ta+(hi-sa)*(tb-ta)/(sb-sa)
        low_age=tleft-F(cohort.birth)
        high_age=tright-F(cohort.birth)
        if low_age>bound:continue
        if high_age<=bound:total+=hi-lo
        else:
            width=(bound-low_age)*(hi-lo)/(high_age-low_age)
            total+=max(F(0),min(hi-lo,width))
    return total


def test_exact_162_independent_source_mass_integrals_and_quantiles():
    assert service_dominates(MIDDLE,SLOW)
    assert service_dominates(FAST,MIDDLE)
    assert service_dominates(FAST,SLOW)
    checks=0
    for curve,horizon,route,age in product(
            (SLOW,MIDDLE,FAST),
            (F(3),F(7),F(10)),
            (1,2),
            (F(0),F(1,2),F(1),F(2),F(3),F(4),F(5),F(7),F(10))):
        x=FiniteFIFOQuantiles(SOURCE,curve,horizon)
        direct=sum(
            direct_source_label_mass_by_inverse(b,curve,horizon,age)
            for b in SOURCE if b.route==route
        )/x.route_mass(route)
        assert direct==x.cdf(route,age)
        checks+=1
    assert checks==162
    for horizon,route,age in product(
            (F(3),F(7),F(10)),(1,2),
            (F(0),F(1),F(3),F(7),F(10))):
        s=FiniteFIFOQuantiles(SOURCE,SLOW,horizon)
        f=FiniteFIFOQuantiles(SOURCE,FAST,horizon)
        assert s.cdf(route,age)<=f.cdf(route,age)
        assert s.completion(route)<=f.completion(route)


def test_conservative_input_fixed_quantile_order_across_exact_rational_levels():
    for horizon in (F(3),F(7),F(10)):
        slow=FiniteFIFOQuantiles(SOURCE,SLOW,horizon)
        fast=FiniteFIFOQuantiles(SOURCE,FAST,horizon)
        for route,p in product((1,2),[F(i,16) for i in range(1,17)]):
            old=slow.quantile(route,p)
            new=fast.quantile(route,p)
            assert new is not None or old is None
            if new is not None and old is not None:
                assert new<=old
