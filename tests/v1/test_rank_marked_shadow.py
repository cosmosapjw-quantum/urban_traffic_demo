from fractions import Fraction as F
import random
import pytest
from metroflow.v1.rank_marked_shadow import CumulativeMarkedFIFO, MarkSpan, MODEL_VERSION


def span(n,p,c,b=0,ready=0,route="r",cls="car"):
    return MarkSpan(F(n),F(p),F(c),F(b),F(ready),route,cls)


def test_marked_mass_and_birth_moment_exact():
    x=CumulativeMarkedFIFO()
    x.enter(span(3,2,1,b=2,ready=10,route="red"))
    x.enter(span(4,5,3,b=9,ready=10,route="blue"))
    assert x.arrived()==(F(7),F(26),F(15),F(42))
    assert x.serve(F(4),F(10))==(F(4),F(11),F(6),F(15))
    assert x.stock()==(F(3),F(15),F(9),F(27))
    assert x.arrived()==tuple(a+b for a,b in zip(x.exited(),x.stock()))
    assert [s.route for _,s in x.outgoing_marks(F(2),F(4))]==["red","blue"]


def test_exact_finite_response_fifo_blocks_ready_later_route():
    x=CumulativeMarkedFIFO()
    x.enter(span(1,3,0,ready=5,route="first"))
    x.enter(span(1,7,0,ready=0,route="second"))
    before=x.stock()
    with pytest.raises(ValueError):
        x.serve(F(1,8),F(1))
    assert x.stock()==before
    assert x.serve(F(1,2),F(6))[1]==F(3,2)
    assert x.serve(F(3,2),F(6))[1]==F(17,2)


def test_one_source_span_does_not_multiply_by_service_count():
    x=CumulativeMarkedFIFO()
    x.enter(span(1,F(7,2),F(5,3)))
    for i in range(8192):
        x.serve(F(1,8192),F(i+1))
    assert x.source_span_count==1
    assert x.departed_rank==F(1)
    assert x.stock()==(F(0),)*4
    assert x.exited()==x.arrived()


def test_mass_and_birth_moments_do_not_suffice_for_eligibility():
    x=CumulativeMarkedFIFO()
    y=CumulativeMarkedFIFO()
    x.enter(span(1,1,0,ready=0,b=0))
    x.enter(span(1,1,0,ready=2,b=2))
    y.enter(span(2,1,0,ready=1,b=1))
    assert x.stock()==y.stock()
    assert x.ready_prefix(F(3,2))==F(1)
    assert y.ready_prefix(F(3,2))==F(2)


def test_exact_residence_time_occupancy_identity():
    x=CumulativeMarkedFIFO()
    x.enter(span(1,2,0))
    x.enter(span(1,5,0))
    q0=x.stock()
    flux=x.serve(1,1)
    q1=x.stock()
    x.serve(1,2)
    # Integrate queue occupancy over [0,2], stepwise constant between service times.
    area=tuple(a+b for a,b in zip(q0,q1))
    # first vehicle exits at 1 s; second exits at 2 s.
    assert area[0]==F(3)
    assert area[1]==F(12)
    assert area[1]==2*1+5*2
    assert flux[1]==F(2)


def test_eager_fifo_oracle_random_exact_rational():
    rng=random.Random(20261123)
    x=CumulativeMarkedFIFO()
    eager=[]
    for i in range(42):
        s=span(F(rng.randrange(1,8),16),F(rng.randrange(1,6),3),
               F(rng.randrange(0,5),7),b=F(i,4),ready=F(i,4),
               route=f"route{i%7}",cls=f"class{i%3}")
        x.enter(s)
        eager.append([s.vehicles,s])
    for k in range(225):
        left=x.entered_rank-x.departed_rank
        if not left: break
        ask=min(left,F(rng.randrange(1,5),40))
        old=x.departed_rank
        got=x.serve(ask,F(50))
        required=ask
        expected=[F(0)]*4
        while required:
            amount,s=eager[0]
            take=min(amount,required)
            for j,r in enumerate(s.rate()):
                expected[j]+=take*r
            amount-=take
            required-=take
            if amount:eager[0][0]=amount
            else:eager.pop(0)
        assert got==tuple(expected)
        assert sum(m for m,_ in eager)==x.stock()[0]
        assert tuple(a+b for a,b in zip(x.exited(),x.stock()))==x.arrived()
        assert x.departed_rank-old==ask


def test_invalid_mass_and_float_rejected():
    x=CumulativeMarkedFIFO()
    x.enter(span(1,1,1))
    with pytest.raises(TypeError):
        x.serve(0.1,1)
    with pytest.raises(ValueError):
        x.serve(2,1)
    assert x.departed_rank==0
    assert MODEL_VERSION=="rank_marked_flow_v0_exact_rational"


def test_reject_negative_or_decreasing_clocks_and_prebirth_eligibility():
    with pytest.raises(ValueError):
        span(1,1,0,b=2,ready=1)
    x=CumulativeMarkedFIFO()
    x.enter(span(1,1,0))
    x.serve(F(1,2),F(2))
    old=x.departed_rank
    with pytest.raises(ValueError):
        x.serve(F(1,2),F(1))
    assert x.departed_rank==old
